#!/usr/bin/env python3
"""
CLI entrypoint for Steve Capital x OOBE SAP MCP x MultiHopper Autonomous Agent.
"""

from __future__ import annotations

import argparse
import dataclasses
import http.server
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.capital_engine import (  # noqa: E402
    compute_barbell_strategy,
    delegate_subagent_vault,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, serve_stdio  # noqa: E402


def run_demo() -> dict:
    strategy = compute_barbell_strategy(DEFAULT_MANDATE)
    subagent = delegate_subagent_vault(
        DEFAULT_MANDATE,
        subagent_id="subagent-commodity-basis-01",
        role="Adrena Synthetic Gold & Oil Basis Hedger",
        vault_address="SubVltAdrena8xK3mP9qR2wT5yU7nJ4hL6zB1cV9kLmN",
        allocated_budget_usd=150.0,
        max_single_tx_usd=75.0,
        allowed_protocols=("adrena", "phoenix"),
    )
    route = plan_multihopper_route(
        DEFAULT_MANDATE,
        input_token="SOL",
        input_amount=0.85,
        output_token="USDC",
        recipients=[
            {
                "wallet": "SubVltAdrena8xK3mP9qR2wT5yU7nJ4hL6zB1cV9kLmN",
                "label": "Adrena Basis Sub-Agent Vault",
                "share_bps": 6000,
            },
            {
                "wallet": "KamVltYield4pQ7sT2xW9vK3mN8rY5uJ1hL6zB4cDefG",
                "label": "Kamino USDC Yield Reserve Vault",
                "share_bps": 4000,
            },
        ],
    )
    guardrail_sample = evaluate_mandate_action(
        DEFAULT_MANDATE,
        protocol="adrena",
        notional_usd=120.0,
        leverage=2.0,
        pyth_conf_bps=12,
    )
    return {
        "mandate_policy_digest": DEFAULT_MANDATE.policy_digest(),
        "barbell_strategy": strategy,
        "subagent_delegation": dataclasses.asdict(subagent),
        "multihopper_compliant_route": route,
        "adrena_execution_guardrail": guardrail_sample,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Steve Capital Autonomous Agent & MCP Server")
    parser.add_argument("--demo", action="store_true", help="Run full mandate + barbell + MultiHopper simulation")
    parser.add_argument("--mcp-stdio", action="store_true", help="Run MCP 2024-11-05 JSON-RPC server over STDIO")
    parser.add_argument("--serve-http", type=int, metavar="PORT", help="Run HTTP MCP endpoint on 127.0.0.1:PORT")
    args = parser.parse_args(argv)

    if args.mcp_stdio:
        serve_stdio()
        return 0
    if args.serve_http:
        httpd = http.server.HTTPServer(("127.0.0.1", args.serve_http), McpHttpHandler)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
        return 0

    print(json.dumps(run_demo(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
