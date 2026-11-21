# Submission & Operator Runbook — Steve Capital Autonomous Capital Agent Challenge (`v4.0.0`)

## Live Artifacts Shipped (`v4.0.0`)
- **Public GitHub Repo:** `https://github.com/jeffrey-graham/steve-capital-solana-agent`
- **Live Interactive Web Control Plane (GitHub Pages):** `https://jeffrey-graham.github.io/steve-capital-solana-agent/`
- **SAP v2 / Metaplex MPL Core Metadata Passport:** `https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json`
- **Live `x402` v1 SPL USDC Discovery Manifest:** `https://jeffrey-graham.github.io/steve-capital-solana-agent/.well-known/x402.json`
- **OpenGraph / MPL Core Card (`HTTP 200`):** `https://jeffrey-graham.github.io/steve-capital-solana-agent/og.png`
- **Finalized On-Chain `0x80` `VersionedTransaction (v0)` Mandate Anchor (Solana Devnet Slot `524,729,972`):**
  - Signer Wallet: `3pcmw8VQooZne1LehScj8FoWjtRF9nJqNfD8h8c5VmmY`
  - Solana Explorer: `https://explorer.solana.com/tx/4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e?cluster=devnet`
  - Solscan: `https://solscan.io/tx/4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e?cluster=devnet`
- **Local Test & Lint Verification:** `python3 -m unittest discover -s tests -v` (`46/46 passing`) & `python3 -m ruff check src tests` (`0 errors`)
- **Live `$0`-Spend Solana Mainnet-Beta `simulateTransaction` (`v0 + ALT`):** `python3 src/cli.py --simulate-mainnet` (`err: null`, `34,260 CU`, Mainnet ALT `2immgwYNHBbyVQKVGCEkgWpi53bLwWNRMB5G2nbgYV17` + MultiHopper Core/Orchestrator/Token2022 Hook verified executable)
- **Pre-Drafted X Showcase Thread:** `X_SHOWCASE_THREAD.md`

## External Platform & On-Chain Capital Gates (Verbatim Superteam Earn Audit)
Per the official Superteam Earn challenge specification (`https://earn.superteam.fun/listings/bounty/build-an-autonomous-capital-agent-on-solana-and-compete-for-dollar500-in-rewards`, deadline `2026-12-10T22:59:59Z`):
1. **Main Bounty (`$250 USDC` across 3 spots: `$125 / $75 / $50`):** Requires deploying an autonomous agent on `https://steve.oobeprotocol.ai/`, funding the agent wallet with **at least 20 USDC (or equivalent SOL)** on Solana mainnet, recording verified Arena XP activity, providing the agent wallet address + Solana Explorer/Solscan links, and posting on X tagging `@OOBEonSol` and `@SteveCapitalOS`.
2. **MultiHopper Side-Track (`$125 USDC` across 3 spots: `$60` Highest Volume, `$40` Most Transfers, `$25` Best Agent Integration):** Requires executing qualifying Solana mainnet MultiHopper route(s) originating from your registered Steve Capital agent wallet + posting on X tagging `@Multihopper`, `@OOBEonSol`, and `@SteveCapitalOS`.
3. **Ace Data Cloud Side-Track (`$125` across 2 spots: `$75 USDC` + `$50` Ace credits):** Requires connecting `ace-mcp` (`https://api.acedata.cloud/mcp`), completing at least **5 paid requests using purchased Ace credits** (`platform.acedata.cloud` — free trial/promotional credits do not count), and posting on X tagging `@acedatacloud`, `@OOBEonSol`, and `@SteveCapitalOS`.

Because we strictly enforce zero unauthorized mainnet capital spending and zero fabricated transaction signatures (`GEMINI.md` §4–5), `StevePulse v4.0.0` ships 100% of the open-source 15-tool + 3-prompt SAP MCP server, OOBE SAP v2 Agent Identity Passport + `0.1 SOL` treasury fee auditor, Steve Launchpad anti-rug auditor, Sybil-resistant Arena XP & `x402` payment verifier, finalized Solana Devnet `0x80` `v0` transaction anchor (`4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e`), live Mainnet `v0 + ALT` `simulateTransaction` dry-run telemetry (`err: null`, `34,260 CU`), MultiHopper 10-tier fee & two-phase `confirm-broadcast` planner, 30-day walk-forward regime stress backtester, Agent Space specialist sub-agent DAG verifier, 46-test suite, and interactive GitHub Pages control plane.
