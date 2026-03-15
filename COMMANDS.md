# RugRadar — Commands for Hermes

You can use the following in natural language in Hermes CLI or Telegram. The agent follows the RugRadar procedure in AGENTS.md.

---

## Token analysis

```
Analyze token: 0x1234567890abcdef1234567890abcdef12345678
```

```
Analyze rug risk for this token: 0xabc... (full contract address)
```

```
Produce a trust report for token 0x...
```

---

## Wallet (deployer) analysis

```
Analyze wallet: 0x9876543210fedcba9876543210fedcba98765432
```

```
Review this wallet's history and rug risk: 0x...
```

```
What tokens has deployer 0x... launched before; is it trustworthy?
```

---

## Short / alternative forms

```
Rug check: 0x...
```

```
Risk analysis for 0x...
```

```
Is this address safe? 0x...
```

---

## Solana / meme coin

```
Analyze solana token: MINT_ADDRESS
```

```
Analyze this Solana meme coin: [mint or token address]
```

```
Rug check solana: [base58 address]
```

Sending only a Solana mint/wallet address (long base58 string) is enough; the bot treats it as an analysis request.

---

## Specifying chain (optional)

```
Analyze token 0x... on BSC
```

```
Analyze token 0x... on Ethereum
```

---

## Repeat / comparison

```
Do you remember the tokens I had analyzed before?
```

```
Compare these two tokens: 0x... and 0x...
```

---

## Copy-paste examples

**First analysis:**
```
Analyze token: 0x1234567890abcdef1234567890abcdef12345678
```

**Wallet only:**
```
Analyze wallet: 0xabcdef1234567890abcdef1234567890abcdef
```

---

## How to run Hermes

1. **CLI:** From the project folder (the directory you cloned; AGENTS.md must be here):
   ```bash
   cd /path/to/your-cloned-repo
   hermes chat
   ```
   Then in the chat:
   ```
   Analyze token: 0x...
   ```

2. **Telegram:** If the bridge is running, send the same sentence in Telegram; the agent follows the same procedure (AGENTS.md should be in the project directory or set as context in Hermes home).

3. **Toolsets:** Web and code execution are needed. If missing:
   ```bash
   hermes chat --toolsets "web,terminal,code_execution,delegation"
   ```

---

## API keys (optional)

Using Etherscan/BSCScan API keys gives more stable data. Add to `.env`:

```
ETHERSCAN_API_KEY=YourKey
BSCSCAN_API_KEY=YourKey
```

See **APIS.md** for all keys. Without keys, the agent can still use **web_search** / **web_extract** to gather info from public pages.
