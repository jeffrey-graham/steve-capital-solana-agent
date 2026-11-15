#!/usr/bin/env python3
"""
CLI entrypoint for Steve Capital x OOBE SAP MCP x MultiHopper x Ace Data Cloud Agent.
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

from src.capital_engine import (
    compute_barbell_strategy,
    delegate_subagent_vault,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, serve_stdio
from src.partner_integrations import (
    plan_magicblock_private_settlement,
    synthesize_acedata_macro_brief,
)
from src.solana_telemetry import inspect_solana_arena_wallet


def run_demo() -> dict:
    strategy = compute_barbell_strategy(DEFAULT_MANDATE)
    subagent = delegate_subagent_vault(
        DEFAULT_MANDATE,
        subagent_id="subagent-commodity-basis-01",
        role="Adrena Synthetic Gold & Oil Basis Hedger",
        vault_address="4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
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
                "wallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
                "label": "Adrena Basis Sub-Agent Vault",
                "share_bps": 6000,
            },
            {
                "wallet": "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj",
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
    ace_brief = synthesize_acedata_macro_brief(
        DEFAULT_MANDATE,
        paid_ledger=[
            {
                "request_id": f"ace-req-00{i}",
                "tool_name": tool,
                "status": "succeeded",
                "credit_source": "purchased",
                "credits_spent": 0.25,
                "query_fingerprint": f"fp-unique-signal-{i}",
                "timestamp_unix": 1763200000 + i * 60,
            }
            for i, tool in enumerate(
                (
                    "ace_google_search",
                    "ace_deep_research",
                    "ace_tts_narrate",
                    "ace_image_render",
                    "ace_video_brief",
                ),
                start=1,
            )
        ],
    )
    magicblock_settlement = plan_magicblock_private_settlement(
        DEFAULT_MANDATE,
        token="USDC",
        amount=80.0,
        recipient_wallet="8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj",
        session_ttl_seconds=900,
    )
    return {
        "mandate_policy_digest": DEFAULT_MANDATE.policy_digest(),
        "barbell_strategy": strategy,
        "subagent_delegation": dataclasses.asdict(subagent),
        "multihopper_compliant_route": route,
        "adrena_execution_guardrail": guardrail_sample,
        "acedata_macro_brief": ace_brief,
        "magicblock_private_settlement": magicblock_settlement,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Steve Capital Autonomous Agent & MCP Server")
    parser.add_argument("--demo", action="store_true", help="Run full 3-track simulation")
    parser.add_argument("--mcp-stdio", action="store_true", help="Run MCP JSON-RPC server over STDIO")
    parser.add_argument("--serve-http", type=int, metavar="PORT", help="Run HTTP MCP endpoint on 127.0.0.1:PORT")
    parser.add_argument("--check-wallet", type=str, metavar="PUBKEY", help="Inspect live Solana Mainnet-Beta wallet Arena readiness")
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
    if args.check_wallet:
        report = inspect_solana_arena_wallet(args.check_wallet)
        print(json.dumps(report, indent=2))
        return 0

    print(json.dumps(run_demo(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
