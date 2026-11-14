# StevePulse — Autonomous Capital & MultiHopper Guardrail Engine (OOBE SAP MCP)

**StevePulse** (`steve-capital-solana-agent`) is a deterministic Python SDK, Model Context Protocol (`MCP 2024-11-05`) tool server, and interactive web control plane built for **Steve Capital** (powered by **OOBE Protocol SAP MCP**) and **MultiHopper** on Solana.

- **Live Interactive Control Plane:** [https://jeffrey-graham.github.io/steve-capital-solana-agent/](https://jeffrey-graham.github.io/steve-capital-solana-agent/)
- **Repository:** [https://github.com/jeffrey-graham/steve-capital-solana-agent](https://github.com/jeffrey-graham/steve-capital-solana-agent)

## Architecture & Core Modules

1. **Programmable Mandate & Anti-Abuse Gate (`src/capital_engine.py`)**
   - Enforces Steve Capital Arena funding floors (`>= $20 USDC`), per-transaction caps, 24-hour rolling spend budgets, portfolio drawdown circuit breakers, Pyth oracle confidence bounds (`conf_bps <= max_pyth_conf_bps`), and TRM Labs counterparty risk ceilings.
   - Deterministically blocks prohibited self-transfers (`origin == destination`), duplicate recipient splits, and circular `A -> B -> A` wash-trading loops before an agent signs or delegates capital.
   - Emits SHA-256 verifiable execution receipts (`steve:receipt:v1:<digest>`).

2. **Quarter-Kelly Barbell Strategy Allocator (`compute_barbell_strategy`)**
   - Sizes positions across **Kamino** USDC lending vaults, **Meteora DLMM** liquidity bins, **Phoenix** orderbook maker carry, and **Adrena** synthetic commodity perpetuals (`XAU-PERP`, `WTI-PERP`) while preserving an exact `10,000 bps` conservation invariant and capping single volatile sleeves at `<= 3,000 bps`.

3. **Monotone Sub-Agent Vault Delegation (`delegate_subagent_vault`)**
   - Provisions isolated specialist sub-agent vaults whose budgets, single-tx limits, drawdown auto-revocation thresholds, and protocol allowlists are mathematically constrained to be strict subsets of the parent mandate (preventing privilege escalation).

4. **MultiHopper Non-Custodial `v0 + ALT` Route Planner (`plan_multihopper_route`)**
   - Plans split-routed multi-recipient Solana disbursements while counting origin principal **strictly once per route** regardless of intermediate DEX hops.
   - Verifies Address Lookup Table (`ALT`) compression inside Solana's `1,232-byte` `VersionedTransaction (v0)` packet ceiling.

5. **MCP `2024-11-05` Server (`src/mcp_server.py`)**
   - Exposes `steve_evaluate_mandate`, `steve_compute_barbell_strategy`, `steve_delegate_subagent_vault`, and `multihopper_plan_compliant_route` over both JSON-RPC 2.0 `STDIO` and `HTTP POST /mcp`.

## Quickstart & Verification

```bash
# Run the full 10-test unit, invariant, and live HTTP MCP transport suite (stdlib Python 3.10+)
python3 -m unittest discover -s tests -v

# Run the CLI demonstration (Mandate + Barbell + Sub-Agent + MultiHopper v0 plan)
python3 src/cli.py --demo

# Start the MCP 2024-11-05 server over STDIO for Steve Capital / Claude / SAP MCP Workspace
python3 src/cli.py --mcp-stdio
```
