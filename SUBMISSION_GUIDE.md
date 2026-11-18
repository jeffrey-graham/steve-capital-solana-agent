# Submission & Operator Runbook — Steve Capital Autonomous Capital Agent Challenge (`v2.0.0`)

## Live Artifacts Shipped (`v2.0.0`)
- **Public GitHub Repo:** `https://github.com/jeffrey-graham/steve-capital-solana-agent`
- **Live Interactive Web Control Plane (GitHub Pages):** `https://jeffrey-graham.github.io/steve-capital-solana-agent/`
- **Local Test & Lint Verification:** `python3 -m unittest discover -s tests -v` (`27/27 passing`) & `python3 -m ruff check src tests` (`0 errors`)
- **Walk-Forward Regime Stress Backtester:** `python3 src/cli.py --backtest`
- **Live Solana Mainnet Readiness Check:** `python3 src/cli.py --check-wallet <SOLANA_PUBKEY>`
- **Pre-Drafted X Showcase Thread:** `X_SHOWCASE_THREAD.md`

## External Platform & On-Chain Capital Gates (Verified Status)
Per the official Superteam Earn challenge specification (`https://earn.superteam.fun/listings/bounty/build-an-autonomous-capital-agent-on-solana-and-compete-for-dollar500-in-rewards`, deadline `2026-12-10T22:59:59Z`):
1. **Main Bounty (`$250 USDC` across 3 spots):** Requires funding a registered Steve Capital agent wallet at `https://steve.oobeprotocol.ai/` with **at least 20 USDC (or equivalent SOL)** on Solana mainnet, recording verified Arena XP activity, and posting on X tagging `@OOBEonSol` and `@SteveCapitalOS`.
2. **MultiHopper Side-Track (`$125 USDC` across 3 spots, incl. `$25` Best Agent Integration):** Requires executing at least 1 real Solana mainnet MultiHopper route originating from your registered Steve Capital agent wallet + posting on X tagging `@Multihopper`, `@OOBEonSol`, and `@SteveCapitalOS`.
3. **Ace Data Cloud Side-Track (`$125` across 2 spots):** Requires connecting `ace-mcp` (`https://api.acedata.cloud/mcp`), completing at least **5 paid requests using purchased Ace credits** (`platform.acedata.cloud` — free trial credits do not count), and posting on X tagging `@acedatacloud`, `@OOBEonSol`, and `@SteveCapitalOS`.
4. **Superteam Earn Submission Credit Gate:** Submitting on `superteam.fun/earn` requires `>= 1` Superteam Earn submission credit (replenishes when pending judged bounties resolve or on monthly reset).

Because we strictly enforce zero unauthorized capital spending and zero fabricated transaction hashes (`GEMINI.md` §4–5), `StevePulse v2.0.0` ships 100% of the open-source 10-tool MCP server, 30-day walk-forward regime stress backtester, Agent Space specialist sub-agent DAG verifier, live Solana RPC wallet inspector, Quarter-Kelly allocator, MultiHopper `v0+ALT` planner, Ace Data Cloud regime synthesizer + 5-purchased-credit verifier, MagicBlock Ephemeral Rollup guardrail, 27-test suite, and live GitHub Pages control plane ready to attach as soon as a `>= 20 USDC` Steve Capital agent wallet and Superteam credit are available.
