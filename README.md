# RugRadar — On-Chain Reputation & Rug Risk Agent

> Token and wallet rug-pull risk and trustworthiness analysis with Hermes Agent. Use from Telegram with a single command.

---

## Run with one command (Telegram bridge)

After installing Hermes and setting your Telegram bot token, **one command** starts the bot. Users send “Analyze token 0x…” in Telegram; **Hermes Agent** runs the analysis and the report is sent back via the bot.

### Requirements

- **Python 3.x**
- **Hermes Agent** installed ([Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation))
- **Telegram Bot Token** (free from [@BotFather](https://t.me/BotFather))

### Setup and run

```bash
# 1. Clone the repo, then go into the project directory
#    (folder name = whatever you cloned, e.g. "rugradar" if you ran: git clone .../rugradar.git)
git clone https://github.com/YOUR_USER/rugradar.git
cd rugradar

# 2. Create .env and add your API keys (required)
cp .env.example .env
# Edit .env and add at least:
#   TELEGRAM_BOT_TOKEN=...   (required for the bot; get from @BotFather)
# For better token data (EVM + Solana), also add keys — see APIS.md:
#   ETHERSCAN_API_KEY=...
#   BSCSCAN_API_KEY=...
#   BIRDEYE_API_KEY=...
#   GOPLUS_API_KEY=...
# (.env is not in the repo — never commit real keys.)
# Before any push, run: git status — .env must NOT appear in the list.

# 3. Run
python rugradar_bot.py
```

On Windows use `copy .env.example .env` instead of `cp`.

That’s it. The bot runs; token/wallet analysis requests sent in Telegram are forwarded to Hermes and the reply is sent to the user.

### Usage in Telegram

- `/start` or `/help` — short usage info
- `Analyze token: 0x...` — token rug analysis
- `Rug check: 0x...` — same analysis
- `0x...` (address only) — treated as analysis request

Analysis is performed by **Hermes Agent** (AGENTS.md procedure, web/terminal/code/delegation tools). May take 1–2 minutes.

---

## Using Hermes directly (CLI)

To use Hermes from the terminal without Telegram:

```bash
cd /path/to/rugradar   # or whatever your project folder is
hermes chat --toolsets "web,terminal,code_execution,delegation"
```

Then in the chat:

```
Analyze token: 0xCONTRACT_ADDRESS
Analyze wallet: 0xWALLET_ADDRESS
```

Command reference: **COMMANDS.md**

---

## Project structure

| File | Description |
|------|-------------|
| **rugradar_bot.py** | Telegram ↔ Hermes bridge; run this to start the bot. |
| **rugradar_api.py** | Fetches token data from DexScreener, Birdeye, GoPlus, etc. |
| **AGENTS.md** | RugRadar procedure — Hermes reads this for every analysis. |
| **APIS.md** | API keys and data sources. |
| **COMMANDS.md** | User command summary. |
| **.env.example** | Example env; copy to `.env` and add `TELEGRAM_BOT_TOKEN`. |
| **requirements.txt** | Bridge uses stdlib only; Hermes is installed separately. |

---

## API keys (add to .env)

You **must** create a `.env` file from `.env.example` and add at least `TELEGRAM_BOT_TOKEN`.  
For richer reports (token data, LP lock, top holders, GitHub activity), add these to `.env` — see **APIS.md** for where to get each key:

```
ETHERSCAN_API_KEY=...
BSCSCAN_API_KEY=...
BIRDEYE_API_KEY=...
GOPLUS_API_KEY=...
```

See **APIS.md** for all keys. Hermes’ LLM provider (OpenRouter, Nous, etc.) should be configured with its own keys (`hermes setup` or `~/.hermes/config.yaml`).

---

## Built for

Hermes Agent Hackathon · [Nous Research](https://nousresearch.com/)

---

*Not financial advice. Rug score is an estimate; do your own research.*
