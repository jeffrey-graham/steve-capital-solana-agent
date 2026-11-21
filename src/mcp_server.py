"""
Steve Capital x OOBE SAP MCP x MultiHopper x Ace Data Cloud — MCP Server
========================================================================
Provides JSON-RPC 2.0 STDIO and Streamable HTTP transports compatible with
OOBE SAP MCP (`2025-06-18` & `2024-11-05`) and Steve Capital MCP Workspace
(`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`,
`resources/list`, `resources/read`).
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import sys
from typing import Any

from src.arena_backtester import (
    plan_agent_space_delegation_dag,
    run_walk_forward_regime_backtest,
)
from src.capital_engine import (
    DEFAULT_MARKET_SNAPSHOT,
    MandatePolicy,
    MandateViolationError,
    compute_barbell_strategy,
    delegate_subagent_vault,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.launchpad_and_arena import (
    audit_steve_launchpad_manifest,
    build_x402_payment_challenge,
    score_verified_arena_xp_ledger,
    verify_x402_agent_payment_envelope,
)
from src.partner_integrations import (
    plan_magicblock_private_settlement,
    synthesize_acedata_macro_brief,
)
from src.sap_identity_and_sim import (
    build_sap_agent_identity_passport,
    simulate_solana_v0_dry_run,
)
from src.solana_telemetry import inspect_solana_arena_wallet

MCP_SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

MCP_SERVER_INFO = {
    "name": "steve-capital-multihopper-guardian",
    "version": "4.0.0",
    "vendor": "OOBE SAP MCP, MultiHopper & Ace Data Cloud Ecosystem Builder",
    "protocolVersion": "2025-06-18",
    "transport": "streamable-http",
}

STEVE_MCP_WORKSPACE_CONFIG = {
    "mcpServers": {
        "sap": {
            "type": "http",
            "url": "https://mcp.sap.oobeprotocol.ai/mcp",
            "transport": "streamable-http",
        },
        "mh-docs": {
            "type": "http",
            "url": "https://dev-docs.multihopper.com/mcp",
            "transport": "streamable-http",
        },
        "mh-api": {
            "type": "http",
            "url": "https://multihopper.com/api/mcp",
            "transport": "streamable-http",
            "credentialClass": "env-managed",
        },
        "ace-mcp": {
            "type": "http",
            "url": "https://api.acedata.cloud/mcp",
            "transport": "streamable-http",
            "credentialClass": "env-managed",
        },
        "steve-capital-guardian": {
            "type": "http",
            "url": "http://127.0.0.1:8787/mcp",
            "transport": "streamable-http",
        },
    }
}

DEFAULT_MANDATE = MandatePolicy(
    mandate_id="mandate-steve-main-001",
    owner_wallet="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    agent_wallet="9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    funded_balance_usd=500.0,
    max_single_tx_usd=200.0,
    max_rolling_24h_spend_usd=600.0,
    max_slippage_bps=60,
    max_portfolio_drawdown_bps=500,
    max_perp_leverage=2.5,
    max_pyth_conf_bps=30,
)

MCP_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "steve_evaluate_mandate",
        "description": "Evaluate an onchain action (Kamino, Meteora, Adrena XAU/WTI, Phoenix, MagicBlock, MultiHopper) against programmable Steve Capital guardrails, TRM risk screening, and anti-wash rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "description": "Target Solana protocol identifier."},
                "notional_usd": {"type": "number", "description": "USD value of the proposed action."},
                "rolling_24h_spent_usd": {"type": "number", "default": 0.0},
                "current_drawdown_bps": {"type": "integer", "default": 0},
                "estimated_slippage_bps": {"type": "integer", "default": 15},
                "leverage": {"type": "number", "default": 1.0},
                "pyth_conf_bps": {"type": "integer", "default": 8},
                "trm_risk_score": {"type": "integer", "default": 0},
                "destination_wallets": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["protocol", "notional_usd"],
        },
    },
    {
        "name": "steve_compute_barbell_strategy",
        "description": "Compute a Pyth-confidence-gated Quarter-Kelly Barbell capital allocation across Kamino USDC yield, Meteora DLMM, Phoenix, and Adrena synthetic commodities (XAU/WTI).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "dry_powder_floor_bps": {"type": "integer", "default": 1500},
                "max_pyth_conf_bps": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "steve_delegate_subagent_vault",
        "description": "Provision an isolated sub-agent vault policy with monotone privilege containment (strictly bounded by parent Steve Capital mandate limits).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subagent_id": {"type": "string"},
                "role": {"type": "string"},
                "vault_address": {"type": "string"},
                "allocated_budget_usd": {"type": "number"},
                "max_single_tx_usd": {"type": "number"},
                "allowed_protocols": {"type": "array", "items": {"type": "string"}},
                "existing_delegated_usd": {"type": "number", "default": 0.0},
            },
            "required": [
                "subagent_id",
                "role",
                "vault_address",
                "allocated_budget_usd",
                "max_single_tx_usd",
                "allowed_protocols",
            ],
        },
    },
    {
        "name": "multihopper_plan_compliant_route",
        "description": "Plan a non-custodial MultiHopper multi-recipient route with single-count principal verification, TRM screening, anti-circular/self-transfer checks, and Solana v0+ALT byte compression.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_token": {"type": "string", "default": "SOL"},
                "input_amount": {"type": "number"},
                "output_token": {"type": "string", "default": "USDC"},
                "recipients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "wallet": {"type": "string"},
                            "label": {"type": "string"},
                            "share_bps": {"type": "integer"},
                        },
                        "required": ["wallet", "share_bps"],
                    },
                },
                "intermediate_venues": {"type": "array", "items": {"type": "string"}},
                "trm_max_observed_risk": {"type": "integer", "default": 4},
            },
            "required": ["input_amount", "recipients"],
        },
    },
    {
        "name": "steve_export_kernel_mandate",
        "description": "Export a schema-exact Steve Capital Kernel Mandate JSON payload (`agent.prepare_mandate` / `agent.validate_mandate` compatible on `steve.oobeprotocol.ai`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "approval_threshold_usd": {"type": "number", "default": 100.0},
                "min_liquidity_pct": {"type": "integer", "default": 15},
                "max_protocol_exposure_pct": {"type": "integer", "default": 35},
            },
        },
    },
    {
        "name": "solana_inspect_arena_wallet",
        "description": "Verify a Solana Mainnet-Beta wallet's native SOL and SPL USDC balances against the >= $20 USD Steve Capital Arena funding floor using live RPC + Pyth Hermes v2.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet_address": {"type": "string", "description": "Base58 32-byte Solana wallet public key."},
                "sol_price_usd": {"type": "number", "description": "Optional SOL/USD override for deterministic simulation."},
            },
            "required": ["wallet_address"],
        },
    },
    {
        "name": "acedata_macro_regime_brief",
        "description": "Synthesize Ace Data Cloud MCP search/research signals + Pyth spreads into a Steve Capital regime recommendation, TTS script, and optional >= 5 purchased-credit side-track eligibility audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pyth_sol_conf_bps": {"type": "integer", "default": 9},
                "pyth_xau_conf_bps": {"type": "integer", "default": 12},
                "signals": {"type": "array", "items": {"type": "object"}},
                "paid_ledger": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
    {
        "name": "magicblock_plan_private_transfer",
        "description": "Plan a confidential SPL token settlement via MagicBlock Ephemeral Rollups with pre-shielding TRM screening, anti-self-transfer checks, and bounded session-key TTLs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "default": "USDC"},
                "amount": {"type": "number"},
                "recipient_wallet": {"type": "string"},
                "session_ttl_seconds": {"type": "integer", "default": 900},
                "commit_interval_ms": {"type": "integer", "default": 5000},
                "trm_risk_score": {"type": "integer", "default": 3},
            },
            "required": ["amount", "recipient_wallet"],
        },
    },
    {
        "name": "steve_backtest_barbell_regimes",
        "description": "Run a 30-day walk-forward regime stress backtest comparing StevePulse Quarter-Kelly Barbell + Pyth/Drawdown Circuit-Breaker against Uncapped Equal-Weight DeFi and Passive Kamino USDC.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "dry_powder_floor_bps": {"type": "integer", "default": 1500},
                "max_pyth_conf_bps": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "steve_plan_agent_space_dag",
        "description": "Plan and verify a multi-specialist sub-agent delegation DAG in Steve Capital Agent Space enforcing reserve conservation, pairwise Base58 vault isolation, monotone privilege containment, and acyclic inter-agent settlements.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "min_parent_reserve_bps": {"type": "integer", "default": 1500},
                "specs": {"type": "array", "items": {"type": "object"}},
                "settlement_edges": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "name": "sap_build_agent_identity_passport",
        "description": "Construct a schema-exact OOBE SAP v2 Agent Identity Passport + Metaplex MPL Core metadata + SNS .sol domain + x402 micro-USDC pricing tier and verify the 0.1 SOL SAP treasury protocol-fee invariant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "StevePulse Guardian"},
                "agent_id": {"type": "string", "default": "stevepulse-guardian"},
                "sns_domain": {"type": "string", "default": "stevepulse.sol"},
                "metadata_uri": {
                    "type": "string",
                    "default": "https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json",
                },
                "price_per_call_micro_usdc": {"type": "integer", "default": 1000},
                "observed_treasury_lamports_delta": {"type": "integer", "default": 100000000},
            },
        },
    },
    {
        "name": "solana_simulate_v0_dry_run",
        "description": "Compile a binary Solana VersionedTransaction (v0, 0x80) with Address Lookup Table (ALT) account compression and run a $0-spend simulateTransaction dry-run against Solana Mainnet-Beta.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memo_tag": {"type": "string", "default": "StevePulse-v4:MandateVerified"},
                "compute_unit_limit": {"type": "integer", "default": 300000},
                "allow_offline_fallback": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "steve_audit_launchpad_token",
        "description": "Audit a proposed Steve Launchpad token launch against anti-rug invariants (revoked mint/freeze authority, >= $50 initial USDC liquidity, <= 20% insider allocation, <= 2.5% Token-2022 transfer fee, public HTTPS/IPFS metadata) and parent mandate limits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "token_name": {"type": "string"},
                "token_symbol": {"type": "string"},
                "metadata_uri": {"type": "string"},
                "initial_liquidity_usdc": {"type": "number"},
                "total_supply": {"type": "integer", "default": 1000000000},
                "creator_allocation_bps": {"type": "integer", "default": 1000},
                "mint_authority_revoked": {"type": "boolean", "default": True},
                "freeze_authority_revoked": {"type": "boolean", "default": True},
                "token2022_transfer_fee_bps": {"type": "integer", "default": 0},
                "graduation_market_cap_usd": {"type": "number", "default": 69000.0},
            },
            "required": ["token_name", "token_symbol", "metadata_uri", "initial_liquidity_usdc"],
        },
    },
    {
        "name": "steve_score_arena_xp_ledger",
        "description": "Compute Sybil-resistant verified Steve Arena XP across official challenge categories while excluding < $20 USD wallets, self-transfers, circular routes, duplicate tx signatures, and category spam bursts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "funded_balance_usd": {"type": "number", "default": 500.0},
                "require_finalized_onchain": {"type": "boolean", "default": True},
                "activities": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["activities"],
        },
    },
    {
        "name": "sap_verify_x402_payment",
        "description": "Generate an HTTP 402 (x402 v1 Solana SPL USDC) challenge and verify an incoming agent-to-agent payment envelope with anti-replay nonce, expiry, Base58 pubkey, and TRM counterparty screening.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string", "default": "stevepulse:macro-regime-feed"},
                "price_micro_usdc": {"type": "integer", "default": 1000},
                "nonce": {"type": "string", "default": "x402-nonce-stevepulse-001"},
                "expires_at_unix": {"type": "integer", "default": 1800000000},
                "current_unix": {"type": "integer", "default": 1795300000},
                "consumed_nonces": {"type": "array", "items": {"type": "string"}},
                "payment_envelope": {"type": "object"},
            },
            "required": ["payment_envelope"],
        },
    },
]

MCP_PROMPTS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "autonomous-rebalance-cycle",
        "description": "Execute a full Steve Capital autonomous market-regime check, Quarter-Kelly Barbell sizing, and Mainnet v0+ALT dry-run verification.",
        "arguments": [
            {"name": "wallet_address", "description": "Solana Mainnet-Beta agent wallet address", "required": False}
        ],
    },
    {
        "name": "multihopper-treasury-disbursement",
        "description": "Plan a TRM-screened, single-principal MultiHopper v0+ALT split route with two-phase confirm-broadcast verification.",
        "arguments": [
            {"name": "input_sol", "description": "Origin SOL principal to route across specialist vaults", "required": False}
        ],
    },
    {
        "name": "launchpad-due-diligence",
        "description": "Run anti-rug authority, liquidity, and metadata verification before launching or buying a Steve Launchpad token.",
        "arguments": [
            {"name": "token_symbol", "description": "Candidate Launchpad ticker symbol", "required": True}
        ],
    },
]


def _policy_with_overrides(args: dict[str, Any]) -> MandatePolicy:
    funded = float(args.get("funded_balance_usd", DEFAULT_MANDATE.funded_balance_usd))
    max_conf = int(args.get("max_pyth_conf_bps", DEFAULT_MANDATE.max_pyth_conf_bps))
    return dataclasses.replace(
        DEFAULT_MANDATE,
        funded_balance_usd=funded,
        max_pyth_conf_bps=max_conf,
    )


def handle_mcp_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """
    Processes a single JSON-RPC 2.0 MCP message.
    Returns None for JSON-RPC notifications (messages without an `id` member).
    """
    is_notification = "id" not in request
    req_id = request.get("id")
    method = str(request.get("method", ""))
    params = request.get("params") or {}

    if method in ("notifications/initialized", "notifications/cancelled") and is_notification:
        return None

    if method == "initialize":
        requested_version = str(params.get("protocolVersion", "2024-11-05"))
        negotiated_version = (
            requested_version
            if requested_version in MCP_SUPPORTED_PROTOCOL_VERSIONS
            else "2024-11-05"
        )
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": negotiated_version,
                "serverInfo": MCP_SERVER_INFO,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
            },
        }

    if method in ("ping", "notifications/initialized", "initialized"):
        return None if is_notification else {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS_SCHEMA}}

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": MCP_PROMPTS_SCHEMA}}

    if method == "prompts/get":
        pname = str(params.get("name", ""))
        pargs = params.get("arguments") or {}
        valid_names = {p["name"] for p in MCP_PROMPTS_SCHEMA}
        if pname not in valid_names:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown prompt: {pname}"},
            }
        wallet_hint = str(pargs.get("wallet_address") or DEFAULT_MANDATE.agent_wallet)
        text = (
            f"Execute workflow '{pname}' for Steve Capital agent wallet {wallet_hint}: "
            "1) Call solana_inspect_arena_wallet to verify >= $20 USD Arena funding; "
            "2) Call acedata_macro_regime_brief and steve_compute_barbell_strategy; "
            "3) Verify mandate guardrails via steve_evaluate_mandate and solana_simulate_v0_dry_run."
        )
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "description": f"Autonomous StevePulse operator workflow: {pname}",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            },
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": [
                    {
                        "uri": "steve://mandates/default-policy",
                        "name": "Default Steve Capital Programmable Mandate Policy",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "steve://markets/solana-defi-snapshot",
                        "name": "Solana DeFi & Adrena Commodity Opportunity Snapshot",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "steve://mcp-workspace/config",
                        "name": "OOBE SAP MCP + MultiHopper + Ace Data Cloud Streamable-HTTP Config",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "steve://sap/identity-passport",
                        "name": "OOBE SAP v2 Agent Identity Passport (Metaplex MPL Core + SNS + x402)",
                        "mimeType": "application/json",
                    },
                ]
            },
        }

    if method == "resources/read":
        uri = str(params.get("uri", ""))
        if uri == "steve://mandates/default-policy":
            body = dataclasses.asdict(DEFAULT_MANDATE)
            body["policy_digest"] = DEFAULT_MANDATE.policy_digest()
            body["steve_kernel_mandate"] = DEFAULT_MANDATE.to_steve_kernel_mandate()
        elif uri == "steve://markets/solana-defi-snapshot":
            body = {"markets": [dataclasses.asdict(m) for m in DEFAULT_MARKET_SNAPSHOT]}
        elif uri == "steve://mcp-workspace/config":
            body = STEVE_MCP_WORKSPACE_CONFIG
        elif uri == "steve://sap/identity-passport":
            body = build_sap_agent_identity_passport(DEFAULT_MANDATE)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown resource URI: {uri}"},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "contents": [
                    {"uri": uri, "mimeType": "application/json", "text": json.dumps(body, indent=2)}
                ]
            },
        }

    if method == "tools/call":
        tool_name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        try:
            policy = _policy_with_overrides(args)
            if tool_name == "steve_evaluate_mandate":
                payload = evaluate_mandate_action(
                    policy,
                    protocol=str(args["protocol"]),
                    notional_usd=float(args["notional_usd"]),
                    rolling_24h_spent_usd=float(args.get("rolling_24h_spent_usd", 0.0)),
                    current_drawdown_bps=int(args.get("current_drawdown_bps", 0)),
                    estimated_slippage_bps=int(args.get("estimated_slippage_bps", 15)),
                    leverage=float(args.get("leverage", 1.0)),
                    pyth_conf_bps=int(args.get("pyth_conf_bps", 8)),
                    trm_risk_score=int(args.get("trm_risk_score", 0)),
                    destination_wallets=args.get("destination_wallets"),
                )
            elif tool_name == "steve_compute_barbell_strategy":
                payload = compute_barbell_strategy(
                    policy,
                    dry_powder_floor_bps=int(args.get("dry_powder_floor_bps", 1500)),
                )
            elif tool_name == "steve_delegate_subagent_vault":
                delegation = delegate_subagent_vault(
                    policy,
                    subagent_id=str(args["subagent_id"]),
                    role=str(args["role"]),
                    vault_address=str(args["vault_address"]),
                    allocated_budget_usd=float(args["allocated_budget_usd"]),
                    max_single_tx_usd=float(args["max_single_tx_usd"]),
                    allowed_protocols=list(args["allowed_protocols"]),
                    existing_delegated_usd=float(args.get("existing_delegated_usd", 0.0)),
                )
                payload = dataclasses.asdict(delegation)
            elif tool_name == "multihopper_plan_compliant_route":
                payload = plan_multihopper_route(
                    policy,
                    input_token=str(args.get("input_token", "SOL")),
                    input_amount=float(args["input_amount"]),
                    output_token=str(args.get("output_token", "USDC")),
                    recipients=list(args["recipients"]),
                    intermediate_venues=tuple(
                        args.get("intermediate_venues") or ("Meteora DLMM", "Orca Whirlpool")
                    ),
                    trm_max_observed_risk=int(args.get("trm_max_observed_risk", 4)),
                )
            elif tool_name == "steve_export_kernel_mandate":
                payload = policy.to_steve_kernel_mandate(
                    approval_threshold_usd=float(args.get("approval_threshold_usd", 100.0)),
                    min_liquidity_pct=int(args.get("min_liquidity_pct", 15)),
                    max_protocol_exposure_pct=int(args.get("max_protocol_exposure_pct", 35)),
                )
            elif tool_name == "solana_inspect_arena_wallet":
                sol_override = args.get("sol_price_usd")
                payload = inspect_solana_arena_wallet(
                    str(args["wallet_address"]),
                    sol_price_usd=float(sol_override) if sol_override is not None else None,
                )
            elif tool_name == "acedata_macro_regime_brief":
                payload = synthesize_acedata_macro_brief(
                    policy,
                    signals=args.get("signals"),
                    pyth_sol_conf_bps=int(args.get("pyth_sol_conf_bps", 9)),
                    pyth_xau_conf_bps=int(args.get("pyth_xau_conf_bps", 12)),
                    paid_ledger=args.get("paid_ledger"),
                )
            elif tool_name == "magicblock_plan_private_transfer":
                payload = plan_magicblock_private_settlement(
                    policy,
                    token=str(args.get("token", "USDC")),
                    amount=float(args["amount"]),
                    recipient_wallet=str(args["recipient_wallet"]),
                    session_ttl_seconds=int(args.get("session_ttl_seconds", 900)),
                    commit_interval_ms=int(args.get("commit_interval_ms", 5000)),
                    trm_risk_score=int(args.get("trm_risk_score", 3)),
                )
            elif tool_name == "steve_backtest_barbell_regimes":
                payload = run_walk_forward_regime_backtest(
                    policy,
                    dry_powder_floor_bps=int(args.get("dry_powder_floor_bps", 1500)),
                )
            elif tool_name == "steve_plan_agent_space_dag":
                payload = plan_agent_space_delegation_dag(
                    policy,
                    specs=args.get("specs"),
                    settlement_edges=args.get("settlement_edges"),
                    min_parent_reserve_bps=int(args.get("min_parent_reserve_bps", 1500)),
                )
            elif tool_name == "sap_build_agent_identity_passport":
                payload = build_sap_agent_identity_passport(
                    policy,
                    name=str(args.get("name", "StevePulse Guardian")),
                    agent_id=str(args.get("agent_id", "stevepulse-guardian")),
                    sns_domain=str(args.get("sns_domain", "stevepulse.sol")),
                    metadata_uri=str(
                        args.get(
                            "metadata_uri",
                            "https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json",
                        )
                    ),
                    price_per_call_micro_usdc=int(args.get("price_per_call_micro_usdc", 1000)),
                    observed_treasury_lamports_delta=int(
                        args.get("observed_treasury_lamports_delta", 100_000_000)
                    ),
                )
            elif tool_name == "solana_simulate_v0_dry_run":
                payload = simulate_solana_v0_dry_run(
                    policy,
                    memo_tag=str(args.get("memo_tag", "StevePulse-v4:MandateVerified")),
                    compute_unit_limit=int(args.get("compute_unit_limit", 300_000)),
                    allow_offline_fallback=bool(args.get("allow_offline_fallback", True)),
                )
            elif tool_name == "steve_audit_launchpad_token":
                payload = audit_steve_launchpad_manifest(
                    policy,
                    token_name=str(args["token_name"]),
                    token_symbol=str(args["token_symbol"]),
                    metadata_uri=str(args["metadata_uri"]),
                    initial_liquidity_usdc=float(args["initial_liquidity_usdc"]),
                    total_supply=int(args.get("total_supply", 1_000_000_000)),
                    creator_allocation_bps=int(args.get("creator_allocation_bps", 1000)),
                    mint_authority_revoked=bool(args.get("mint_authority_revoked", True)),
                    freeze_authority_revoked=bool(args.get("freeze_authority_revoked", True)),
                    token2022_transfer_fee_bps=int(args.get("token2022_transfer_fee_bps", 0)),
                    graduation_market_cap_usd=float(args.get("graduation_market_cap_usd", 69_000.0)),
                )
            elif tool_name == "steve_score_arena_xp_ledger":
                payload = score_verified_arena_xp_ledger(
                    policy,
                    list(args.get("activities") or []),
                    require_finalized_onchain=bool(args.get("require_finalized_onchain", True)),
                )
            elif tool_name == "sap_verify_x402_payment":
                challenge = build_x402_payment_challenge(
                    policy,
                    service_id=str(args.get("service_id", "stevepulse:macro-regime-feed")),
                    price_micro_usdc=int(args.get("price_micro_usdc", 1000)),
                    nonce=str(args.get("nonce", "x402-nonce-stevepulse-001")),
                    expires_at_unix=int(args.get("expires_at_unix", 1_800_000_000)),
                )
                verification = verify_x402_agent_payment_envelope(
                    policy,
                    challenge,
                    dict(args.get("payment_envelope") or {}),
                    current_unix=int(args.get("current_unix", 1_795_300_000)),
                    consumed_nonces=list(args.get("consumed_nonces") or []),
                )
                payload = {"challenge": challenge, "verification": verification}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        except (MandateViolationError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Guardrail/Validation Error: {exc}"}],
                    "isError": True,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                "structuredContent": payload,
                "isError": False,
            },
        }

    if is_notification:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_mcp_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


class McpHttpHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/health", "/mcp/health"):
            body = json.dumps({"ok": True, "server": MCP_SERVER_INFO}).encode("utf-8")
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self._send_cors()
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self.send_response(404)
            self._send_cors()
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        req = json.loads(raw.decode("utf-8"))
        resp = handle_mcp_request(req)
        if resp is None:
            self.send_response(204)
            self._send_cors()
            self.end_headers()
            return
        body = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
