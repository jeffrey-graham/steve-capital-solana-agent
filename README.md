# StevePulse v1.2 — Autonomous Capital, MultiHopper & Ace Data Cloud Engine (OOBE SAP MCP)

**StevePulse** (`steve-capital-solana-agent`) is a zero-dependency Python SDK, Model Context Protocol (`MCP 2025-06-18` & `2024-11-05`) server, live Solana Mainnet-Beta wallet inspector, and interactive web control plane built for the **Steve Capital Agent Challenge** (**OOBE Protocol SAP MCP** + **MultiHopper** + **Ace Data Cloud** + **MagicBlock**).

- **Live Interactive Control Plane:** [https://jeffrey-graham.github.io/steve-capital-solana-agent/](https://jeffrey-graham.github.io/steve-capital-solana-agent/)
- **Repository:** [https://github.com/jeffrey-graham/steve-capital-solana-agent](https://github.com/jeffrey-graham/steve-capital-solana-agent)

## Architecture & Full 3-Track Coverage

1. **Programmable Mandate, Kernel Schema & Anti-Abuse Gate (`src/capital_engine.py`)**
   - Enforces Steve Capital Arena funding floors (`>= $20 USD`), per-transaction caps, 24-hour rolling spend budgets, portfolio drawdown circuit breakers, Pyth oracle confidence bounds (`conf_bps <= max_pyth_conf_bps`), and TRM Labs counterparty risk ceilings.
   - Exports schema-exact `steve.oobeprotocol.ai` Kernel Mandate payloads (`to_steve_kernel_mandate`) and blocks prohibited self-transfers (`origin == destination`), duplicate recipient splits, and circular `A -> B -> A` wash-trading loops.

2. **Quarter-Kelly Barbell Strategy & Monotone Sub-Agent Vaults (`src/capital_engine.py`)**
   - Sizes positions across **Kamino** USDC lending vaults, **Meteora DLMM** liquidity bins, **Phoenix** orderbook maker carry, and **Adrena** synthetic commodity perpetuals (`XAU-PERP`, `WTI-PERP`) with an exact `10,000 bps` conservation invariant and `<= 3,000 bps` volatile-sleeve caps.
   - Provisions isolated sub-agent vaults (`delegate_subagent_vault`) mathematically constrained to strict subsets of parent mandate privileges.

3. **Live Solana Mainnet-Beta Wallet & Oracle Telemetry (`src/solana_telemetry.py`)**
   - Validates 32-byte Base58 Solana public keys and queries Solana Mainnet-Beta JSON-RPC (`getBalance` + `getTokenAccountsByOwner` for USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`) alongside Pyth Hermes v2 (`PYTH_HERMES_API_KEY`) with automatic zero-key spot fallback (`coinbase_spot_fallback`) to audit `>= $20 USD` Steve Arena eligibility in real time.

4. **MultiHopper Non-Custodial `v0 + ALT` Route Planner (`src/capital_engine.py`)**
   - Plans split-routed multi-recipient Solana disbursements while counting origin principal **strictly once per route** regardless of intermediate DEX hops, verifying `1,232-byte` `VersionedTransaction (v0)` + Address Lookup Table (`ALT`) compression and `/api/multihopper/broadcast` hop groups (`<= 25`).

5. **Ace Data Cloud MCP Macro Brief & MagicBlock Ephemeral Rollup Privacy (`src/partner_integrations.py`)**
   - **Ace Data Cloud Side-Track:** Synthesizes Ace MCP search/research signals + Pyth spreads into regime transitions (`RISK_ON_BARBELL_CARRY`, `COMMODITY_INFLATION_HEDGE`, `DEFENSIVE_DELEVERAGE`), narrated TTS/video briefing scripts, and strict `>= 5` **purchased-credit** side-track verification (excluding `free_trial`, `promotional`, and duplicate query fingerprints).
   - **MagicBlock Private Settlements:** Plans confidential SPL token settlements inside scoped Ephemeral Rollup sessions (`60s..3600s` TTL) while enforcing pre-shielding TRM counterparty screening and anti-self-transfer rules.

6. **MCP `2025-06-18` & `2024-11-05` Server (`src/mcp_server.py` & `mcp.workspace.json`)**
   - Exposes all **8 tools** (`steve_evaluate_mandate`, `steve_compute_barbell_strategy`, `steve_delegate_subagent_vault`, `multihopper_plan_compliant_route`, `steve_export_kernel_mandate`, `solana_inspect_arena_wallet`, `acedata_macro_regime_brief`, `magicblock_plan_private_transfer`) over both `STDIO` and Streamable `HTTP POST /mcp`.

## Quickstart & Verification

```bash
# Run the 19-test unit, invariant, RPC/Pyth, Ace Data Cloud, MagicBlock, and live HTTP MCP suite
python3 -m unittest discover -s tests -v

# Run the full 3-track CLI simulation
python3 src/cli.py --demo

# Inspect any live Solana Mainnet-Beta wallet for >= $20 USD Steve Arena readiness
python3 src/cli.py --check-wallet 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU

# Start the MCP server over STDIO for Steve Capital / Claude / SAP MCP Workspace
python3 src/cli.py --mcp-stdio
```
