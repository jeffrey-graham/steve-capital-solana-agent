# StevePulse v4.0 — Autonomous Capital, SAP v2 Passport, Steve Launchpad, MultiHopper & Agent Space Engine (OOBE SAP MCP)

**StevePulse v4.0** (`steve-capital-solana-agent`) is a zero-dependency Python SDK, **15-tool + 3-prompt Model Context Protocol (`MCP 2025-06-18`, `2025-03-26` & `2024-11-05`) server**, OOBE **SAP v2 Agent Identity Passport** builder, **Steve Launchpad** anti-rug guardrail, Sybil-resistant **Arena XP** & **x402** micro-USDC payment verifier, binary Solana `VersionedTransaction (v0)` + Address Lookup Table (`ALT`) compiler, 30-day walk-forward regime stress backtester, multi-agent delegation DAG orchestrator, and interactive web control plane built for the **Steve Capital Agent Challenge** (**OOBE Protocol SAP MCP** + **MultiHopper** + **Ace Data Cloud** + **MagicBlock**).

- **Live Interactive Control Plane:** [https://jeffrey-graham.github.io/steve-capital-solana-agent/](https://jeffrey-graham.github.io/steve-capital-solana-agent/)
- **SAP v2 / Metaplex MPL Core Metadata Passport:** [https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json](https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json)
- **Live HTTP `402` (`x402` v1 SPL USDC) Discovery Manifest:** [https://jeffrey-graham.github.io/steve-capital-solana-agent/.well-known/x402.json](https://jeffrey-graham.github.io/steve-capital-solana-agent/.well-known/x402.json)
- **Finalized On-Chain `0x80` `VersionedTransaction (v0)` Mandate Anchor (Solana Devnet Slot `524,729,972`):** [`4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e`](https://explorer.solana.com/tx/4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e?cluster=devnet) ([Solscan](https://solscan.io/tx/4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e?cluster=devnet))
- **Repository:** [https://github.com/jeffrey-graham/steve-capital-solana-agent](https://github.com/jeffrey-graham/steve-capital-solana-agent)

## Full Challenge Scope & Architecture

1. **Programmable Mandate, Kernel Schema & Anti-Abuse Gate (`src/capital_engine.py`)**
   - Enforces Steve Capital Arena funding floors (`>= $20 USD`), per-transaction caps, 24-hour rolling spend budgets, portfolio drawdown circuit breakers, Pyth oracle confidence bounds (`conf_bps <= max_pyth_conf_bps`), and TRM Labs counterparty risk ceilings.
   - Exports schema-exact `steve.oobeprotocol.ai` Kernel Mandate payloads (`to_steve_kernel_mandate`) and blocks prohibited self-transfers (`origin == destination`), duplicate recipient splits, and circular `A -> B -> A` wash-trading loops.

2. **Quarter-Kelly Barbell Strategy & Monotone Sub-Agent Vaults (`src/capital_engine.py`)**
   - Sizes positions across **Kamino** USDC lending vaults, **Meteora DLMM** liquidity bins, **Phoenix** orderbook maker carry, and **Adrena** synthetic commodity perpetuals (`XAU-PERP`, `WTI-PERP`) with an exact `10,000 bps` conservation invariant and `<= 3,000 bps` volatile-sleeve caps.
   - Provisions isolated sub-agent vaults (`delegate_subagent_vault`) mathematically constrained to strict subsets of parent mandate privileges.

3. **OOBE SAP v2 Agent Identity Passport, Metaplex MPL Core, SNS & x402 Bridge (`src/sap_identity_and_sim.py`, `src/launchpad_and_arena.py`)**
   - Implements the official OOBE SAP MCP Agent Identity Pipeline (`sap_payments_register_agent` local-signer boundary — hosted MCP never custodies keypairs).
   - Audits the `100,000,000` lamport (`0.1 SOL`) SAP Treasury registration fee invariant (`J7PyZAGKvprCz4SQ5DKBLAHstJxgVqZcz6kguUoWpP7P`), failing closed (`protocolComplete: false`) on missing/underpaid fees, rejecting local desktop file URIs, normalizing `.sol` SNS domains, and verifying incoming agent-to-agent `x402` SPL USDC payment envelopes with anti-replay nonces and TRM screening.

4. **Binary Solana `v0 + ALT` Compiler, Mainnet `simulateTransaction` & Finalized On-Chain Anchor (`src/sap_identity_and_sim.py`)**
   - Encodes byte-exact `0x80` `VersionedMessageV0` packets (`compact-u16` tables, `ComputeBudget` CU limit/price instructions, SPL `Memo` mandate receipts, and real Mainnet Address Lookup Table `2immgwYNHBbyVQKVGCEkgWpi53bLwWNRMB5G2nbgYV17` 1-byte indices) and runs `simulateTransaction` (`sigVerify: false, replaceRecentBlockhash: true`) live against Solana Mainnet-Beta (`loadedAddresses`, `unitsConsumed: 34,260`, `err: null`).
   - Preserves server-side ephemeral signatures via slot-targeted Ed25519 injection (`inject_signature_at_slot`), verified end-to-end on-chain at Solana Devnet slot `524,729,972` (`4hH9nkdRMjkwXutHvxHs1fgEs4Zw9trqhA8pnBi6AHfpDChbb9cjRx2cev8GM5y5dBPTBr5FqeKrE1ff6KhnZF6e`) and against MultiHopper's three live Mainnet programs (`3jLoS2wbNgtKzieUUxwg6Xhdv6gbZkHDtPWA9ZAgspFh` Core, `4TPCmR2uN3hDM1FbTsf7ZtFXwXGSz4u1Kxv5YHj6eruX` Orchestrator, `2JEv3pD6nczEvn1xDXaEzehkJofPPjoQQpnW5nGY3r52` Token2022 Transfer Hook Guard).

5. **MultiHopper Non-Custodial `v0 + ALT` & Two-Phase Broadcast Planner (`src/capital_engine.py`)**
   - Plans multi-destination disbursements (`<= 20` wallets, `MH_017` guard) while counting origin principal **strictly once per route**, computing the official 10-tier mainnet fee schedule (`0.50%` percent fee split `50/50` = `0.25%` atomic integrator share + Tier 0..9 per-hop lamport fee + `0.002 SOL`/wallet TRM screening fee), and enforcing the two-phase `POST /api/v1/transfers/{id}/confirm-broadcast` sequence (`keeperFundingTx` first -> `MH_039` anti-double-funding guard -> `dispersionInitTxs` `MH_041` exit binding).

6. **Steve Launchpad Anti-Rug Guard & Sybil-Resistant Arena XP Ledger (`src/launchpad_and_arena.py`)**
   - **Steve Launchpad Auditor:** Enforces revoked mint/freeze authorities, `>= $50 USDC` initial liquidity within single-tx mandate limits, `<= 20%` creator supply caps, `<= 2.5%` Token-2022 transfer-fee bounds, and public HTTPS/IPFS/Arweave metadata URIs.
   - **Verified Arena XP Engine:** Scores cross-ecosystem activity across all 6 challenge pillars while filtering `< $20 USD` wallets, self-transfers, circular hops, duplicate signatures, and repetitive category spam bursts.

7. **Ace Data Cloud MCP Macro Brief, MagicBlock ER Privacy & Walk-Forward Backtester (`src/partner_integrations.py`, `src/arena_backtester.py`)**
   - **Ace Data Cloud Side-Track:** Synthesizes Ace MCP search/research signals + Pyth spreads into regime transitions (`RISK_ON_BARBELL_CARRY`, `COMMODITY_INFLATION_HEDGE`, `DEFENSIVE_DELEVERAGE`), narrated TTS/video briefing scripts, and strict `>= 5` **purchased-credit** side-track verification.
   - **MagicBlock Private Settlements & Walk-Forward Backtest:** Plans confidential SPL token settlements inside scoped Ephemeral Rollup sessions (`60s..3600s` TTL) and benchmarks the Pyth-gated Quarter-Kelly Barbell across 30 simulated days of Solana market stress.

8. **MCP `2025-06-18` Server (`src/mcp_server.py` & `mcp.workspace.json`)**
   - Exposes **15 tools**, **4 resources**, and **3 autonomous workflow prompts** (`prompts/list` & `prompts/get`) over both `STDIO` and CORS-enabled Streamable `HTTP POST /mcp`.

## Quickstart & Verification

```bash
# Run the 46-test unit, invariant, binary v0+ALT, SAP v2, Launchpad, Arena XP, x402, and HTTP MCP suite
python3 -m unittest discover -s tests -v

# Run ruff static analysis (0 errors)
python3 -m ruff check src tests

# Run live $0-spend Solana Mainnet-Beta v0+ALT simulateTransaction + MultiHopper program verification
python3 src/cli.py --simulate-mainnet

# Run the full 3-track + v4.0 CLI simulation
python3 src/cli.py --demo

# Run the standalone 30-day walk-forward regime stress backtest
python3 src/cli.py --backtest

# Inspect any live Solana Mainnet-Beta wallet for >= $20 USD Steve Arena readiness
python3 src/cli.py --check-wallet 3pcmw8VQooZne1LehScj8FoWjtRF9nJqNfD8h8c5VmmY

# Start the MCP server over STDIO for Steve Capital / Claude / SAP MCP Workspace
python3 src/cli.py --mcp-stdio
```
