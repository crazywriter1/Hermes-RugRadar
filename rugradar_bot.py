#!/usr/bin/env python3
"""
RugRadar — Telegram bridge to Hermes Agent.

Fetches token data via API (DexScreener, Birdeye, etc.) then passes it to Hermes;
Hermes writes the report from this data (no web search, faster). Hackathon: Hermes at the center.
"""

import os
import sys
import subprocess
import re
import time
import json
from urllib.parse import urlencode
import urllib.request

try:
    from rugradar_api import get_data_for_prompt
except ImportError:
    get_data_for_prompt = None

# Optional: load .env from current directory
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
HERMES_TIMEOUT = int(os.environ.get("HERMES_TIMEOUT", "300"))
TELEGRAM_MAX_MESSAGE = 4096


def hermes_query(message: str, toolsets: str = "web,terminal,code_execution", timeout_sec: int | None = None) -> tuple[str, str | None]:
    """
    Run Hermes Agent. toolsets="skills" + timeout_sec=90 = report from prompt data only (faster).
    """
    timeout_sec = timeout_sec if timeout_sec is not None else HERMES_TIMEOUT
    cmd = [
        "hermes", "chat",
        "--quiet",
        "--yolo",
        "-q", message,
        "--toolsets", toolsets,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ},
            stdin=subprocess.DEVNULL,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if result.returncode != 0 and not out:
            return "", err or f"Hermes exited with code {result.returncode}"
        return out, None
    except FileNotFoundError:
        return "", "Hermes not found. Install: https://hermes-agent.nousresearch.com/docs/getting-started/installation"
    except subprocess.TimeoutExpired:
        return "", f"Hermes timed out after {timeout_sec}s. Try a simpler query."


TELEGRAM_RETRIES = 3
TELEGRAM_TIMEOUT_GET = 65
TELEGRAM_TIMEOUT_SEND = 30


def _telegram_request(req, timeout: int):
    """Retry up to 3 times on connection reset / timeout."""
    last_err = None
    for attempt in range(TELEGRAM_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode()
        except Exception as e:
            last_err = e
            if attempt < TELEGRAM_RETRIES - 1:
                time.sleep(2)
    raise last_err


def telegram_delete_webhook() -> bool:
    """Remove webhook so long polling (getUpdates) can be used. Fixes 409 Conflict."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        body = _telegram_request(req, 15)
        return json.loads(body).get("ok", False)
    except Exception:
        return False


def telegram_get_updates(offset: int | None) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    try:
        req = urllib.request.Request(
            url + "?" + urlencode(params),
            headers={"Accept": "application/json"},
        )
        body = _telegram_request(req, TELEGRAM_TIMEOUT_GET)
        return json.loads(body)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def telegram_send_message(chat_id: int, text: str) -> bool:
    if not text:
        text = "(No response from Hermes.)"
    if len(text) > TELEGRAM_MAX_MESSAGE:
        text = text[: TELEGRAM_MAX_MESSAGE - 80] + "\n\n… (report truncated.)"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        body = _telegram_request(req, TELEGRAM_TIMEOUT_SEND)
        return json.loads(body).get("ok", False)
    except Exception:
        return False


def is_rugradar_request(text: str) -> bool:
    """Heuristic: message looks like token/wallet analysis request."""
    if not text or len(text) > 500:
        return False
    text_lower = text.strip().lower()
    # Ethereum / EVM: 0x + 40 hex chars
    if re.search(r"0x[a-fA-F0-9]{40}", text):
        return True
    # Solana: base58, 32–44 chars (mint/wallet address)
    if re.search(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text):
        return True
    # Explicit keywords
    if any(k in text_lower for k in (
        "analyze", "rug", "risk", "check", "wallet", "token",
        "solana", "sol ", "meme", "raydium", "pump", "birdeye", "solscan"
    )):
        return True
    return False


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set. Create a bot via @BotFather and set the token in .env or environment.")
        sys.exit(1)

    # Quick check that Hermes is available
    try:
        subprocess.run(["hermes", "--version"], capture_output=True, timeout=5, cwd=PROJECT_DIR)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("Warning: 'hermes' not found or not in PATH. Install Hermes first.")
        print("  https://hermes-agent.nousresearch.com/docs/getting-started/installation")

    # 409 Conflict = webhook active or another instance polling; delete webhook so getUpdates works
    if telegram_delete_webhook():
        print("Webhook cleared (was blocking long polling).")
    print("RugRadar bridge running. Send EVM (0x...) or Solana address / 'analyze ...' in Telegram.")
    print("Ctrl+C to stop.")
    print()

    offset = None
    while True:
        try:
            resp = telegram_get_updates(offset)
            if not resp.get("ok"):
                print("Telegram API error:", resp.get("error", resp))
                time.sleep(5)
                continue
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                # /start or /help
                if text in ("/start", "/help", "/rugradar"):
                    telegram_send_message(
                        chat_id,
                        "🛡 RugRadar — Rug risk analysis with Hermes Agent\n\n"
                        "Send an EVM (Ethereum/BSC) or Solana token/wallet address:\n"
                        "• Analyze token: 0x... (EVM)\n"
                        "• Rug check: 0x...\n"
                        "• Solana meme coin: SOL_ADDRESS or analyze solana TOKEN_MINT\n\n"
                        "Supported: Ethereum, BSC, Solana (meme coins included).",
                    )
                    continue

                if not is_rugradar_request(text):
                    telegram_send_message(
                        chat_id,
                        "RugRadar: send a token/wallet address or 'analyze 0x...' / 'analyze solana ...'.",
                    )
                    continue

                telegram_send_message(chat_id, "✅ Received, starting analysis…")

                # 1) API ile veriyi hızlı çek (DexScreener, keysiz)
                api_data = None
                if get_data_for_prompt:
                    addr, api_data = get_data_for_prompt(text)
                    if api_data:
                        telegram_send_message(chat_id, "📡 Data fetched from API, Hermes writing report…")
                        prompt = (
                            "You are the RugRadar agent. The 'TOKEN DATA' and 'SUMMARY / GAPS' sections below are the MAIN SOURCE for the rug risk report. "
                            "Use the same report template for ETH, BSC, Solana and all chains: always evaluate LP lock, GitHub, social, top holder.\n\n"
                            "Required evaluations:\n"
                            "- Top holder %: If data present, write the percentages and assess whale risk; otherwise say 'top holder percentage unknown'.\n"
                            "- LP lock: Always state — is there a lock, unlock date, single-withdrawal risk. (Use GoPlus/DEX data for EVM and Solana.)\n"
                            "- GitHub: If GitHub appears in SUMMARY or raw data, mention it in the report; otherwise say 'GitHub not found'.\n"
                            "- GitHub activity: If '[GitHub Activity]' is present (stars, last push), reflect it positively in reputation score; active repo = trust signal. If no activity, neutral or negative for score.\n"
                            "- Name/Symbol: If present in any source (Birdeye, Helius, Pump.fun, Etherscan/BSCScan), use it.\n"
                            "- Social (website, Twitter, Telegram): If present list them; otherwise say 'not found'.\n\n"
                            "'EXTRA CONTEXT' is news only. Output: Rug Risk (LOW/MEDIUM/HIGH + %), Reputation (0-100), 3-5 signals, 2-3 sentence summary. End with: Not financial advice.\n\n"
                            "Data:\n" + api_data
                        )
                        print("[API] data received, calling Hermes (skills only)...")
                        out, err = hermes_query(prompt, toolsets="skills", timeout_sec=90)
                    else:
                        out, err = None, None
                else:
                    out, err = None, None

                # 2) If no API data or Hermes failed: full Hermes (with web)
                if out is None and err is None:
                    telegram_send_message(chat_id, "⏳ Hermes Agent running (web search may take 1-2 min)…")
                    print(f"[Analysis] {text[:50]}... (no API, full Hermes)")
                    out, err = hermes_query(text)
                elif out is None:
                    out, err = "", err

                print("[Hermes] done.")

                to_send = f"❌ Error: {err[:2000]}" if err else (out or "(Empty response.)")
                ok = telegram_send_message(chat_id, to_send)
                if not ok:
                    print("[WARN] Failed to send to Telegram; retrying in 3s.")
                    time.sleep(3)
                    telegram_send_message(chat_id, to_send)

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print("Error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
