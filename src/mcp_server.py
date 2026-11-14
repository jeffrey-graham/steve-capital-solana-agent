"""
Steve Capital x OOBE SAP MCP x MultiHopper — MCP 2024-11-05 Server
==================================================================
Provides JSON-RPC 2.0 STDIO and HTTP transports compatible with OOBE SAP MCP
and Steve Capital MCP Workspace (`initialize`, `notifications/initialized`,
`ping`, `tools/list`, `tools/call`, `resources/list`, `resources/read`).
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import sys
from typing import Any, Dict, List, Optional

from src.capital_engine import (
    DEFAULT_MARKET_SNAPSHOT,
    MandatePolicy,
    MandateViolationError,
    compute_barbell_strategy,
    delegate_subagent_vault,
    evaluate_mandate_action,
    plan_multihopper_route,
)

MCP_SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")

MCP_SERVER_INFO = {
    "name": "steve-capital-multihopper-guardian",
    "version": "1.1.0",
    "vendor": "OOBE SAP MCP & MultiHopper Ecosystem Builder",
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
    agent_wallet="StvCapAgnt9PqW3vK8mN2xR5tY7uJ4hL6zB1cV9dEfGh",
    funded_balance_usd=500.0,
    max_single_tx_usd=200.0,
    max_rolling_24h_spend_usd=600.0,
    max_slippage_bps=60,
    max_portfolio_drawdown_bps=500,
    max_perp_leverage=2.5,
    max_pyth_conf_bps=30,
)

MCP_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": "steve_evaluate_mandate",
        "description": "Evaluate an onchain action (Kamino, Meteora, Adrena XAU/WTI, Phoenix, MultiHopper) against programmable Steve Capital guardrails, TRM risk screening, and anti-wash rules.",
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
]


def _policy_with_overrides(args: Dict[str, Any]) -> MandatePolicy:
    funded = float(args.get("funded_balance_usd", DEFAULT_MANDATE.funded_balance_usd))
    max_conf = int(args.get("max_pyth_conf_bps", DEFAULT_MANDATE.max_pyth_conf_bps))
    return dataclasses.replace(
        DEFAULT_MANDATE,
        funded_balance_usd=funded,
        max_pyth_conf_bps=max_conf,
    )


def handle_mcp_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                },
            },
        }

    if method in ("ping", "notifications/initialized", "initialized"):
        return None if is_notification else {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS_SCHEMA}}

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
                        "name": "OOBE SAP MCP + MultiHopper MCP Streamable-HTTP Workspace Config",
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
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        except (MandateViolationError, ValueError, KeyError, TypeError) as exc:
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
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/mcp/health"):
            body = json.dumps({"ok": True, "server": MCP_SERVER_INFO}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        req = json.loads(raw.decode("utf-8"))
        resp = handle_mcp_request(req)
        if resp is None:
            self.send_response(204)
            self.end_headers()
            return
        body = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
