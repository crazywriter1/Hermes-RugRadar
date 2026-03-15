#!/usr/bin/env python3
"""
RugRadar — Multi-API token and news data fetcher.
Sources are called when keys are present; data is merged and passed to Hermes (hackathon: Hermes writes the report).
"""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

TIMEOUT = 12
DEBUG = os.environ.get("RUGradar_DEBUG", "").strip().lower() in ("1", "true", "yes")

# Browser-like User-Agent so APIs don't block default urllib
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Optional: load .env
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if v:
                        os.environ.setdefault(k.strip(), v)


_load_env()


def _get(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def _req(url: str, headers: dict | None = None) -> dict | list | None:
    try:
        h = {**DEFAULT_HEADERS, **(headers or {})}
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        if DEBUG:
            print(f"[RUGradar] _req failed: {url[:80]}... -> {e}")
        return None


def _req_rss(url: str) -> list[dict] | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/xml"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            root = ET.fromstring(r.read().decode())
            items = []
            for item in root.findall(".//item")[:10]:
                title = item.find("title")
                link = item.find("link")
                items.append({
                    "title": title.text if title is not None else "",
                    "link": link.text if link is not None else "",
                })
            return items
    except Exception:
        return None


def _extract_address(text: str) -> str | None:
    text = text.strip()
    m = re.search(r"0x[a-fA-F0-9]{40}", text)
    if m:
        return m.group(0)
    m = re.search(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text)
    if m:
        return m.group(0)
    return None


def _is_evm(addr: str) -> bool:
    return addr.startswith("0x")


# ---------- DexScreener (keysiz) ----------
def _format_dexscreener_pairs(address: str, data: dict) -> str | None:
    pairs = data.get("pairs") or data.get("pair") or []
    if isinstance(pairs, dict):
        pairs = [pairs]
    if not pairs:
        return None
    total_liq = 0
    lines = []
    for p in pairs[:15]:
        liq = p.get("liquidity") or p.get("liquidityUsd") or 0
        try:
            total_liq += float(liq)
        except (TypeError, ValueError):
            pass
        lock_info = ""
        for k in ("locked", "liquidityLocked", "lock", "lp_locked"):
            v = p.get(k)
            if v is not None and v != "":
                lock_info = f", {k}={v}"
                break
        lines.append(f"  {p.get('dexId', '?')} ({p.get('chainId', '?')}): liquidity={liq}, priceUsd={p.get('priceUsd', '?')}{lock_info}")
    return (
        f"[DexScreener]\nAddress: {address}\nPair count: {len(pairs)}\nTotal liquidity (USD): {total_liq:.0f}\nDetails:\n" + "\n".join(lines)
    )


def fetch_dexscreener(address: str) -> str | None:
    # 1) Eski/alternatif endpoint: /latest/dex/tokens/{address} (tüm chain'ler)
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
        data = _req(url)
        if data and isinstance(data, dict):
            out = _format_dexscreener_pairs(address, data)
            if out:
                if DEBUG:
                    print("[RUGradar] DexScreener OK (tokens endpoint)")
                return out
    except Exception as e:
        if DEBUG:
            print(f"[RUGradar] DexScreener tokens: {e}")
    # 2) Resmi endpoint: chain bazlı /token-pairs/v1/{chainId}/{tokenAddress}
    for chain_id in ("ethereum", "bsc", "solana", "base", "arbitrum", "polygon"):
        try:
            url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}/{address}"
            data = _req(url)
            if data and isinstance(data, dict):
                out = _format_dexscreener_pairs(address, data)
                if out:
                    if DEBUG:
                        print(f"[RUGradar] DexScreener OK ({chain_id})")
                    return out
            # Bazen liste döner
            if isinstance(data, list) and data:
                out = _format_dexscreener_pairs(address, {"pairs": data})
                if out:
                    if DEBUG:
                        print(f"[RUGradar] DexScreener OK ({chain_id}, list)")
                    return out
        except Exception as e:
            if DEBUG:
                print(f"[RUGradar] DexScreener {chain_id}: {e}")
    if DEBUG:
        print("[RUGradar] DexScreener: no pairs from any endpoint")
    return None


# ---------- CoinDesk RSS (keysiz) ----------
def fetch_coindesk_rss() -> str | None:
    items = _req_rss("https://www.coindesk.com/arc/outboundfeeds/rss/")
    if not items:
        return None
    lines = [f"  - {i['title']}" for i in items[:8]]
    return "[CoinDesk RSS] Son başlıklar:\n" + "\n".join(lines)


# ---------- Etherscan ----------
def fetch_etherscan(address: str) -> str | None:
    key = _get("ETHERSCAN_API_KEY")
    if not key or not _is_evm(address):
        return None
    try:
        url = (
            f"https://api.etherscan.io/api"
            f"?module=token&action=tokeninfo&contractaddress={address}&apikey={key}"
        )
        data = _req(url)
        if not data or data.get("status") != "1" or not data.get("result"):
            return None
        res = data["result"]
        if isinstance(res, str):
            return None
        r = res[0] if isinstance(res, list) else res
        if not isinstance(r, dict):
            return None
        out = [
            f"[Etherscan]\nContract: {address}",
            f"Name: {r.get('name', '?')}",
            f"Symbol: {r.get('symbol', '?')}",
            f"Holder count: {r.get('holder', '?')}",
            f"Verified: {r.get('verified', '?')}",
        ]
        gh = _evm_contract_github("https://api.etherscan.io/api", address, key, "module=contract&action=getsourcecode")
        if gh:
            out.append(f"GitHub: {gh}")
        return "\n".join(out)
    except Exception:
        return None


def _extract_github_urls(text: str) -> list[str]:
    """Metinden https://github.com/owner/repo formatında URL'leri çıkarır (tekrarsız)."""
    seen = set()
    out = []
    for m in re.finditer(r"https?://(?:www\.)?github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:[\s\"'<>)\]]|$)", text):
        repo = m.group(1).rstrip(".,;:)")
        if "/" in repo and repo not in seen and not repo.endswith(".git"):
            seen.add(repo)
            out.append(f"https://github.com/{repo}")
    return out[:3]


def fetch_github_repo_activity(github_url: str) -> str | None:
    """GitHub repo activity — stars, last push, open issues. Used for scoring."""
    m = re.search(r"github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)", github_url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2).rstrip(".,;:)")
    if not owner or not repo:
        return None
    token = _get("GITHUB_TOKEN")
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {**DEFAULT_HEADERS, "Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, dict):
            return None
        stars = data.get("stargazers_count")
        pushed = data.get("pushed_at")
        updated = data.get("updated_at")
        issues = data.get("open_issues_count")
        fork = data.get("fork")
        lines = [f"[GitHub Activity] Repo: {github_url}"]
        if stars is not None:
            lines.append(f"  Stars: {stars}")
        if pushed:
            lines.append(f"  Last push: {pushed}")
        if updated:
            lines.append(f"  Updated: {updated}")
        if issues is not None:
            lines.append(f"  Open issues: {issues}")
        if fork is not None and fork:
            lines.append("  (Fork)")
        if len(lines) > 1:
            return "\n".join(lines)
        return None
    except Exception:
        return None


def _evm_contract_github(base_url: str, address: str, api_key: str, action_query: str) -> str | None:
    """Extract GitHub URL from contract source code API (Etherscan/BSCScan)."""
    try:
        url = f"{base_url}?{action_query}&address={address}&apikey={api_key}"
        data = _req(url)
        if not data or data.get("status") != "1" or not data.get("result"):
            return None
        res = data["result"]
        src = (res[0] if isinstance(res, list) else res).get("SourceCode")
        if not src:
            return None
        # SourceCode bazen { "sources": { ... } } şeklinde gelir
        if isinstance(src, str) and "github.com" in src:
            m = re.search(r"https?://(?:www\.)?github\.com/[^\s\"'<>)\]]+", src)
            if m:
                return m.group(0).rstrip(".,;:)")
        if isinstance(src, dict):
            raw = json.dumps(src)
            if "github.com" in raw:
                m = re.search(r"https?://(?:www\.)?github\.com/[^\s\"'<>)\]]+", raw)
                if m:
                    return m.group(0).rstrip(".,;:)")
        return None
    except Exception:
        return None


# ---------- BSCScan ----------
def fetch_bscscan(address: str) -> str | None:
    key = _get("BSCSCAN_API_KEY")
    if not key or not _is_evm(address):
        return None
    try:
        url = (
            f"https://api.bscscan.com/api"
            f"?module=token&action=tokeninfo&contractaddress={address}&apikey={key}"
        )
        data = _req(url)
        if not data or data.get("status") != "1" or not data.get("result"):
            return None
        res = data["result"]
        if isinstance(res, str):
            return None
        r = res[0] if isinstance(res, list) else res
        if not isinstance(r, dict):
            return None
        out = [
            f"[BSCScan]\nContract: {address}",
            f"Name: {r.get('name', '?')}",
            f"Symbol: {r.get('symbol', '?')}",
            f"Holder: {r.get('holder', '?')}",
        ]
        gh = _evm_contract_github("https://api.bscscan.com/api", address, key, "module=contract&action=getsourcecode")
        if gh:
            out.append(f"GitHub: {gh}")
        return "\n".join(out)
    except Exception:
        return None


# ---------- GoPlus Security (EVM) — all chains, LP lock + token lock ----------
def _fmt_lock_detail_evm(detail_list):
    if not detail_list or not isinstance(detail_list, list):
        return []
    out = []
    for d in detail_list[:5]:
        if not isinstance(d, dict):
            continue
        end = d.get("end_time")
        amt = d.get("amount")
        opt = d.get("opt_time")
        if end:
            out.append(f"unlock: {end}" + (f", amount: {amt}" if amt else ""))
        elif opt:
            out.append(f"locked at: {opt}")
    return out


def fetch_goplus(address: str) -> str | None:
    key = _get("GOPLUS_API_KEY")
    if not key or not _is_evm(address):
        return None
    # Try all EVM chains (use first that returns data)
    chains = [
        ("1", "Ethereum"), ("56", "BSC"), ("42161", "Arbitrum"),
        ("137", "Polygon"), ("10", "Optimism"), ("43114", "Avalanche"), ("8453", "Base"),
    ]
    for chain_id, name in chains:
        try:
            url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={address}"
            req = urllib.request.Request(
                url,
                headers={**DEFAULT_HEADERS, "Authorization": f"Bearer {key}"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read().decode())
            if data.get("code") != 1 or not data.get("result") or address.lower() not in data.get("result", {}):
                continue
            r = data["result"][address.lower()]
            lines = [
                f"[GoPlus Security - {name}]",
                f"Honeypot: {r.get('is_honeypot', '?')}",
                f"Proxy: {r.get('is_proxy', '?')}",
                f"Open source: {r.get('is_open_source', '?')}",
                f"Rug pull risk: {r.get('is_rugpull', '?')}",
            ]
            # LP lock — lp_holders içinde is_locked / locked_detail
            lp_lock_found = False
            for h in (r.get("lp_holders") or [])[:20]:
                if not isinstance(h, dict):
                    continue
                is_locked = h.get("is_locked")
                if is_locked == 1 or is_locked == "1":
                    lp_lock_found = True
                    parts = _fmt_lock_detail_evm(h.get("locked_detail") or [])
                    if parts:
                        lines.append(f"LP lock: YES — {'; '.join(parts)}")
                    else:
                        lines.append("LP lock: YES")
                    break
            if not lp_lock_found:
                lines.append("LP lock: NO or not detected (no lock record)")
            # Token lock — holders
            tok_lock = False
            for h in (r.get("holders") or [])[:5]:
                if not isinstance(h, dict):
                    continue
                if h.get("is_locked") in (1, "1"):
                    tok_lock = True
                    parts = _fmt_lock_detail_evm(h.get("locked_detail") or [])
                    if parts:
                        lines.append(f"Token lock (holder): YES — {'; '.join(parts)}")
                    else:
                        lines.append("Token lock (holder): YES")
                    break
            if not tok_lock and r.get("holders"):
                lines.append("Token lock (holder): NO or not detected")
            return "\n".join(lines)
        except Exception:
            continue
    return None


# ---------- GoPlus Security (Solana) — LP lock, token lock ----------
def fetch_goplus_solana(address: str) -> str | None:
    key = _get("GOPLUS_API_KEY")
    if not key or _is_evm(address):
        return None
    try:
        url = f"https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses={address}"
        req = urllib.request.Request(
            url,
            headers={**DEFAULT_HEADERS, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if data.get("code") != 1 or not data.get("result") or address not in data.get("result", {}):
            return None
        r = data["result"][address]
        lines = ["[GoPlus Security - Solana]"]

        def fmt_lock_detail(detail_list):
            if not detail_list or not isinstance(detail_list, list):
                return []
            out = []
            for d in detail_list[:5]:
                if not isinstance(d, dict):
                    continue
                end = d.get("end_time")
                amt = d.get("amount")
                opt = d.get("opt_time")
                if end:
                    out.append(f"unlock: {end}" + (f", amount: {amt}" if amt else ""))
                if opt and "unlock" not in str(out[-1] if out else ""):
                    out.append(f"locked at: {opt}")
            return out

        # 1) Dex LP holders — liquidity lock
        dex_list = r.get("dex") or r.get("dex_info") or []
        if isinstance(dex_list, dict):
            dex_list = [dex_list]
        lp_lock_found = False
        for dex in dex_list:
            if not isinstance(dex, dict):
                continue
            lp_holders = dex.get("lp_holders") or []
            dex_name = dex.get("dex_name") or dex.get("dexname") or "DEX"
            for h in lp_holders:
                if not isinstance(h, dict):
                    continue
                is_locked = h.get("is_locked")
                if is_locked == 1 or is_locked == "1":
                    lp_lock_found = True
                    locked_detail = h.get("locked_detail") or []
                    parts = fmt_lock_detail(locked_detail)
                    if parts:
                        lines.append(f"LP lock ({dex_name}): YES — {'; '.join(parts)}")
                    else:
                        lines.append(f"LP lock ({dex_name}): YES")
            if not lp_holders and (dex.get("tvl") or dex.get("id")):
                lines.append(f"LP lock ({dex_name}): No data or no lock (could not verify)")
        if not lp_lock_found:
            if dex_list:
                lines.append("LP lock: NO or not detected (no lock record)")
            else:
                lines.append("LP lock: No DEX/liquidity data (pump.fun bonding curve or not listed)")

        # 2) Token holders — token lock (team vb.)
        holders = r.get("holders") or []
        token_lock_found = False
        for h in holders[:5]:
            if not isinstance(h, dict):
                continue
            is_locked = h.get("is_locked")
            if is_locked == 1 or is_locked == "1":
                token_lock_found = True
                locked_detail = h.get("locked_detail") or []
                parts = fmt_lock_detail(locked_detail)
                if parts:
                    lines.append(f"Token lock (holder): YES — {'; '.join(parts)}")
                else:
                    lines.append("Token lock (holder): YES")
                break
        if not token_lock_found and holders:
            lines.append("Token lock (holder): NO or not detected")

        if len(lines) > 1:
            return "\n".join(lines)
        return None
    except Exception:
        return None


# ---------- Birdeye (Solana) ----------
def fetch_birdeye(address: str) -> str | None:
    key = _get("BIRDEYE_API_KEY")
    if not key or _is_evm(address):
        return None
    try:
        url = f"https://public-api.birdeye.so/defi/token_overview?address={address}"
        req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, "X-API-KEY": key})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if not data.get("data"):
            return None
        d = data["data"]
        ext = d.get("extensions") or {}
        lines = [
            f"[Birdeye]\nMint: {address}",
            f"Name: {d.get('name', '?')}",
            f"Symbol: {d.get('symbol', '?')}",
            f"Liquidity: {d.get('liquidity', '?')}",
            f"Holder count: {d.get('holder', '?')}",
        ]
        for key, label in (("website", "Website"), ("twitter", "Twitter"), ("telegram", "Telegram"), ("discord", "Discord"), ("medium", "Medium"), ("github", "GitHub"), ("description", "Description")):
            v = ext.get(key) or d.get(key)
            if v and str(v).strip() and str(v).lower() not in ("null", "none"):
                lines.append(f"{label}: {v}")
        return "\n".join(lines)
    except Exception:
        return None


def fetch_birdeye_top_holders(address: str) -> str | None:
    """Solana: Top holder yüzdeleri (whale risk için). Birdeye holder distribution veya v3 token/holder."""
    key = _get("BIRDEYE_API_KEY")
    if not key or _is_evm(address):
        return None
    try:
        # 1) Holder distribution (top N, supply % ile) — token_address veya address parametresi
        for param_name in ("token_address", "address"):
            try:
                url = (
                    f"https://public-api.birdeye.so/holder/v1/distribution"
                    f"?{param_name}={address}&mode=top&top_n=10&include_list=true"
                )
                req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, "X-API-KEY": key, "x-chain": "solana"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    data = json.loads(r.read().decode())
                if data.get("success") and data.get("data", {}).get("holders"):
                    holders = data["data"]["holders"][:10]
                    lines = ["[Birdeye - Top holders (% of supply)]"]
                    for i, h in enumerate(holders, 1):
                        pct = h.get("percent_of_supply")
                        if pct is not None:
                            pct_str = f"{float(pct) * 100:.2f}%"
                        else:
                            pct_str = "?"
                        lines.append(f"  {i}. {pct_str}")
                    if len(lines) > 1:
                        return "\n".join(lines)
            except Exception:
                continue
    except Exception:
        pass
    try:
        # 2) Fallback: v3 token/holder (top by amount; % yok ama miktar var)
        url = f"https://public-api.birdeye.so/defi/v3/token/holder?address={address}&limit=15"
        req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, "X-API-KEY": key, "x-chain": "solana"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if data.get("success") and data.get("data", {}).get("items"):
            items = data["data"]["items"][:10]
            lines = ["[Birdeye - Top holders (amount)]"]
            for i, h in enumerate(items, 1):
                amt = h.get("ui_amount")
                owner = (h.get("owner") or "?")[:8] + "…"
                if amt is not None:
                    lines.append(f"  {i}. {amt:,.0f} — {owner}")
                else:
                    lines.append(f"  {i}. — {owner}")
            if len(lines) > 1:
                return "\n".join(lines)
    except Exception:
        pass
    return None


# ---------- Helius (Solana metadata) ----------
def fetch_helius(address: str) -> str | None:
    key = _get("HELIUS_API_KEY")
    if not key or _is_evm(address):
        return None
    try:
        url = f"https://api.helius.xyz/v0/token-metadata?api-key={key}"
        req = urllib.request.Request(
            url,
            data=json.dumps({"mintAccounts": [address]}).encode(),
            method="POST",
            headers={**DEFAULT_HEADERS, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if not data:
            return None
        d = data[0] if isinstance(data, list) else data
        name, symbol = d.get("name") or "?", d.get("symbol") or "?"
        off = None
        uri = d.get("uri") or d.get("metadataUri") or (d.get("metadata") or {}).get("uri")
        if uri and isinstance(uri, str) and (not name or name == "?" or not symbol or symbol == "?"):
            try:
                off = _req(uri.strip())
                if isinstance(off, dict):
                    if not name or name == "?":
                        name = off.get("name") or "?"
                    if not symbol or symbol == "?":
                        symbol = off.get("symbol") or "?"
            except Exception:
                pass
        lines = [f"[Helius]\nMint: {address}", f"Name: {name}", f"Symbol: {symbol}"]
        if uri and isinstance(uri, str) and uri.strip():
            lines.append(f"Metadata URI: {uri[:80]}...")
        if isinstance(off, dict):
            for k, label in (("external_url", "External URL"), ("website", "Website"), ("twitter", "Twitter"), ("telegram", "Telegram"), ("discord", "Discord"), ("github", "GitHub")):
                v = off.get(k)
                if v and str(v).strip():
                    lines.append(f"{label}: {v}")
        return "\n".join(lines)
    except Exception:
        return None


# ---------- CryptoPanic (haber) ----------
def fetch_cryptopanic() -> str | None:
    key = _get("CRYPTOPANIC_API_KEY")
    if not key:
        return None
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={key}&public=true"
        data = _req(url)
        if not data or not data.get("results"):
            return None
        lines = [f"  - {p.get('title', '')}" for p in data["results"][:8]]
        return "[CryptoPanic] Son haberler:\n" + "\n".join(lines)
    except Exception:
        return None


# ---------- News API ----------
def fetch_newsapi(query: str = "crypto") -> str | None:
    key = _get("NEWS_API_KEY")
    if not key:
        return None
    try:
        from urllib.parse import quote
        url = f"https://newsapi.org/v2/everything?q={quote(query)}&language=en&pageSize=5&apiKey={key}"
        data = _req(url)
        if not data or not data.get("articles"):
            return None
        lines = [f"  - {a.get('title', '')}" for a in data["articles"][:5]]
        return f"[News API] '{query}' için:\n" + "\n".join(lines)
    except Exception:
        return None


# ---------- Pump.fun (Solana) — public endpoint varsa ----------
# ---------- X (Twitter) API v2 ----------
def fetch_twitter(query: str = "crypto rug") -> str | None:
    token = _get("TWITTER_BEARER_TOKEN")
    if not token:
        return None
    try:
        from urllib.parse import quote
        url = f"https://api.twitter.com/2/tweets/search/recent?query={quote(query)}&max_results=10"
        req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        if not data.get("data"):
            return None
        lines = [f"  - {t.get('text', '')[:100]}..." for t in data["data"][:5]]
        return f"[X API] '{query}' son tweetler:\n" + "\n".join(lines)
    except Exception:
        return None


def fetch_pumpfun(address: str) -> str | None:
    if _is_evm(address):
        return None
    try:
        url = f"https://frontend-api.pump.fun/coins/{address}"
        data = _req(url, headers={"User-Agent": "Mozilla/5.0 (RugRadar)", "Referer": "https://pump.fun/"})
        if not data:
            return None
        if isinstance(data, list) and data:
            data = data[0] if isinstance(data[0], dict) else data
        if isinstance(data, dict):
            data = data.get("data") or data.get("coin") or data
        if not data or not isinstance(data, dict):
            return None
        lines = [f"[Pump.fun] Mint: {address}"]
        for key, label in (
            ("name", "Name"), ("symbol", "Symbol"), ("description", "Description"),
            ("website", "Website"), ("twitter", "Twitter"), ("telegram", "Telegram"), ("discord", "Discord"), ("github", "GitHub"),
            ("image_uri", "Image"), ("bonding_curve_percent", "Bonding curve %"), ("complete", "Bonding complete (LP migrated)"),
            ("liquidity", "Liquidity"), ("market_cap", "Market cap"), ("usd_market_cap", "Market cap USD"),
            ("volume", "Volume"), ("creator", "Creator"), ("created_timestamp", "Created"),
        ):
            v = data.get(key)
            if v is not None and v != "":
                lines.append(f"  {label}: {v}")
        if len(lines) > 1:
            return "\n".join(lines)
        return f"[Pump.fun]\nMint: {address}\n{json.dumps(data, indent=2)[:1000]}\n"
    except Exception:
        return None


def get_data_for_prompt(user_message: str) -> tuple[str | None, str | None]:
    """
    Extract address; group token data and news/social data separately.
    Token section comes first and is labeled so the report is written from it.
    """
    addr = _extract_address(user_message)
    if not addr:
        return None, None

    token_sections = []   # Main source for rug risk
    news_sections = []    # Supporting only

    # Token data (priority)
    d = fetch_dexscreener(addr)
    if d:
        token_sections.append(d)
    if DEBUG:
        print(f"[RUGradar] DexScreener: {'OK' if d else 'no data'}")
    if _is_evm(addr):
        e = fetch_etherscan(addr)
        if e:
            token_sections.append(e)
        b = fetch_bscscan(addr)
        if b:
            token_sections.append(b)
        g = fetch_goplus(addr)
        if g:
            token_sections.append(g)
        if DEBUG:
            print(f"[RUGradar] Etherscan: {'OK' if e else 'no key or no data'}, BSCScan: {'OK' if b else 'no key or no data'}, GoPlus: {'OK' if g else 'no key or no data'}")
    else:
        br = fetch_birdeye(addr)
        if br:
            token_sections.append(br)
        br_holders = fetch_birdeye_top_holders(addr)
        if br_holders:
            token_sections.append(br_holders)
        gs = fetch_goplus_solana(addr)
        if gs:
            token_sections.append(gs)
        hl = fetch_helius(addr)
        if hl:
            token_sections.append(hl)
        pf = fetch_pumpfun(addr)
        if pf:
            token_sections.append(pf)
        if DEBUG:
            print(f"[RUGradar] Birdeye: {'OK' if br else 'no key'}, Top holders: {'OK' if br_holders else 'no'}, GoPlus Solana (LP lock): {'OK' if gs else 'no'}, Helius: {'OK' if hl else 'no'}, Pump.fun: {'OK' if pf else 'no'}")

    # News / social (extra context)
    rss = fetch_coindesk_rss()
    if rss:
        news_sections.append(rss)
    cp = fetch_cryptopanic()
    if cp:
        news_sections.append(cp)
    na = fetch_newsapi("crypto")
    if na:
        news_sections.append(na)
    tw = fetch_twitter("crypto rug")
    if tw:
        news_sections.append(tw)

    # GitHub activity (for scoring) — fetch repo info when GitHub URL is in the data
    combined = "\n".join(token_sections)
    for gh_url in _extract_github_urls(combined):
        gh_activity = fetch_github_repo_activity(gh_url)
        if gh_activity:
            token_sections.append(gh_activity)
            if DEBUG:
                print("[RUGradar] GitHub activity: OK")
            break

    # User always sent an address; Hermes should see it. Return a prompt even when no data (never return addr, None).
    addr_block = f"Requested address: {addr}"
    parts = []

    def _build_summary(sections: list) -> str:
        """Summary that clearly shows gaps: name, symbol, top holder %, LP lock, social."""
        text = "\n".join(sections)
        lines = ["=== SUMMARY / GAPS (evaluate these in the report) ===", addr_block]
        # Name — first occurrence of Name: VALUE (VALUE not empty/?)
        name = None
        for s in sections:
            if "Name:" not in s:
                continue
            i = s.find("Name:") + 5
            rest = s[i:i+120]
            end = rest.find("\n")
            val = (rest[:end] if end >= 0 else rest).strip().strip("?")
            if val and val != "?" and len(val) < 80:
                name = val
                break
        lines.append(f"Name: {name or '— unknown (metadata empty)'}")
        # Symbol
        sym = None
        for s in sections:
            if "Symbol:" not in s:
                continue
            i = s.find("Symbol:") + 7
            rest = s[i:i+50]
            end = rest.find("\n")
            val = (rest[:end] if end >= 0 else rest).strip().strip("?")
            if val and val != "?" and len(val) < 30:
                sym = val
                break
        lines.append(f"Symbol: {sym or '— unknown'}")
        # Top holder %
        has_top = "[Birdeye - Top holders" in text or "Top holders" in text
        lines.append(f"Top holder %: {'(data below) — include in report' if has_top else '— unknown (whale risk not assessed)'}")
        # LP lock
        has_lp = "LP lock" in text
        if "LP lock: YES" in text or "LP lock (" in text and "YES" in text:
            lines.append("LP lock: YES (details below)")
        elif "LP lock: NO" in text or "no lock record" in text:
            lines.append("LP lock: NO or not detected")
        elif has_lp:
            lines.append("LP lock: (summarize the LP lock line below)")
        else:
            lines.append("LP lock: — unknown (no DEX/liquidity data)")
        # Sosyal
        has_social = any(x in text for x in ("Website:", "Twitter:", "Telegram:", "twitter:", "telegram:", "website:"))
        if has_social:
            lines.append("Social (website/Twitter/Telegram): (data below) — include in report")
        else:
            lines.append("Social (website, Twitter, Telegram): — not found (anonymous project)")
        # GitHub
        has_github = "GitHub:" in text and "GitHub: —" not in text
        if has_github:
            lines.append("GitHub: (data below) — include in report")
        else:
            lines.append("GitHub: — not found")
        # GitHub activity (stars, last push) — used for scoring
        has_gh_activity = "[GitHub Activity]" in text
        if has_gh_activity:
            lines.append("GitHub activity (stars, last push): (data below) — positive impact on reputation score")
        else:
            lines.append("GitHub activity: — none (repo info not fetched or no link)")
        return "\n".join(lines)

    if token_sections:
        summary = _build_summary(token_sections)
        parts.append("=== TOKEN DATA (write rug risk report from THIS) ===\n" + summary + "\n\n--- Raw data ---\n\n" + "\n\n".join(token_sections))
    else:
        # API'ler bu adres için boş döndü (pair yok / rate limit / key yok vb.)
        parts.append(
            "=== TOKEN DATA ===\n" + addr_block + "\n"
            "(No data returned for this address from DexScreener, Etherscan/BSCScan (API key may be required) or other sources; "
            "no pair found or API did not respond. Still analyze this address: 0x... for EVM, base58 for Solana. "
            "Give a short assessment; you may state risk is uncertain due to missing data.)"
        )

    if news_sections:
        parts.append("=== EXTRA CONTEXT (news/social) ===\n" + "\n\n".join(news_sections))

    return addr, "\n\n".join(parts)
