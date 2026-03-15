# RugRadar — APIs and API Keys

Add the keys below to your `.env` file. If a key is missing, that source is skipped; at least DexScreener (no key) will work.

---

## No key required

| Source | Purpose |
|--------|--------|
| **DexScreener** | Pairs, liquidity, price (EVM + Solana). No key. |
| **CoinDesk RSS** | General crypto news. No key. |

---

## EVM

| API | .env variable | Where to get key |
|-----|----------------|------------------|
| **Etherscan** | `ETHERSCAN_API_KEY` | [etherscan.io/apis](https://etherscan.io/apis) → Add → Create key |
| **BSCScan** | `BSCSCAN_API_KEY` | [bscscan.com/apis](https://bscscan.com/apis) → Create key |
| **GoPlus Security** | `GOPLUS_API_KEY` | [gopluslabs.io](https://gopluslabs.io) → Token Security API (free tier). EVM: honeypot/rug; **Solana: LP lock / token lock** (Raydium, Streamflow, etc.). |

---

## Solana

| API | .env variable | Where to get key |
|-----|----------------|------------------|
| **Birdeye** | `BIRDEYE_API_KEY` | [birdeye.so](https://birdeye.so) → API / Docs → API Key. Token overview + **top holder %** (whale risk). |
| **Helius** | `HELIUS_API_KEY` | [helius.dev](https://helius.dev) → Dashboard → API Key |
| **Pump.fun** | (public endpoint; key optional) | pump.fun API docs |

---

## News / Sentiment

| API | .env variable | Where to get key |
|-----|----------------|------------------|
| **CryptoPanic** | `CRYPTOPANIC_API_KEY` | [cryptopanic.com](https://cryptopanic.com) → API → auth_token |
| **News API** | `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) → Get API Key |
| **X (Twitter) API v2** | `TWITTER_BEARER_TOKEN` | [developer.twitter.com](https://developer.twitter.com) → Project → Bearer Token (paid tier) |

---

## Scoring (GitHub activity)

- **GitHub Activity:** When a GitHub URL is found in the data, repo info (stars, last push, open issues) is fetched and added to the report; **positive impact on reputation score**.
- **`GITHUB_TOKEN`** (optional): [GitHub → Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens). Without key, API is limited to 60 requests/hour; with token, 5000/hour.

---

## Debugging

- **`RUGradar_DEBUG=1`** — in `.env` or as environment variable. When set, the console logs which APIs return data (DexScreener, Etherscan, BSCScan, etc.). If you get no token data, enable this and run the bot.

---

## Summary

- **Minimum (no keys):** DexScreener + CoinDesk RSS.
- **Recommended:** + Etherscan + BSCScan + Birdeye + GoPlus (rug/honeypot).
- **Full report:** All of the above + CryptoPanic + News API (+ X API optional).

Add keys to `.env` using the same variable names.
