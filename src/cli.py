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

from src.arena_backtester import (
    plan_agent_space_delegation_dag,
    run_walk_forward_regime_backtest,
)
from src.capital_engine import (
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
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, serve_stdio
from src.partner_integrations import (
    plan_magicblock_private_settlement,
    synthesize_acedata_macro_brief,
)
from src.sap_identity_and_sim import (
    build_sap_agent_identity_passport,
    simulate_solana_v0_dry_run,
    verify_multihopper_programs_onchain,
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
    walk_forward_backtest = run_walk_forward_regime_backtest(DEFAULT_MANDATE)
    agent_space_dag = plan_agent_space_delegation_dag(DEFAULT_MANDATE)
    sap_passport = build_sap_agent_identity_passport(DEFAULT_MANDATE)
    launchpad_audit = audit_steve_launchpad_manifest(
        DEFAULT_MANDATE,
        token_name="StevePulse Index Vault",
        token_symbol="SPULSE",
        metadata_uri="https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json",
        initial_liquidity_usdc=125.0,
        creator_allocation_bps=1000,
    )
    arena_xp_ledger = score_verified_arena_xp_ledger(
        DEFAULT_MANDATE,
        [
            {"tx_signature": "5xStratPub11111111111111111111111111111111111", "category": "strategy_publish", "finalized_onchain": True},
            {"tx_signature": "5xMHRoute222222222222222222222222222222222222", "category": "multihopper_mainnet_route", "principal_usd": 157.25, "finalized_onchain": True},
            {"tx_signature": "5xSubVault33333333333333333333333333333333333", "category": "subagent_delegation", "finalized_onchain": True},
            {"tx_signature": "5xAceBrief44444444444444444444444444444444444", "category": "acedata_paid_brief", "finalized_onchain": True},
            {"tx_signature": "5xMagicER555555555555555555555555555555555555", "category": "magicblock_private_settlement", "finalized_onchain": True},
        ],
    )
    x402_challenge = build_x402_payment_challenge(DEFAULT_MANDATE)
    x402_receipt = verify_x402_agent_payment_envelope(
        DEFAULT_MANDATE,
        x402_challenge,
        {
            "payerWallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
            "payTo": DEFAULT_MANDATE.agent_wallet,
            "assetMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amountMicroUsdc": 1000,
            "nonce": x402_challenge["nonce"],
            "txSignature": "4vX402ReceiptSig99999999999999999999999999999999",
            "trmRiskScore": 2,
        },
    )
    return {
        "version": "4.0.0",
        "mandate_policy_digest": DEFAULT_MANDATE.policy_digest(),
        "sap_agent_identity_passport": sap_passport,
        "barbell_strategy": strategy,
        "subagent_delegation": dataclasses.asdict(subagent),
        "agent_space_delegation_dag": agent_space_dag,
        "multihopper_compliant_route": route,
        "adrena_execution_guardrail": guardrail_sample,
        "acedata_macro_brief": ace_brief,
        "magicblock_private_settlement": magicblock_settlement,
        "walk_forward_regime_backtest": walk_forward_backtest,
        "steve_launchpad_audit": launchpad_audit,
        "verified_arena_xp_ledger": arena_xp_ledger,
        "x402_agent_payment_verification": x402_receipt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StevePulse v3.0 — Steve Capital Autonomous Agent & MCP Server")
    parser.add_argument("--demo", action="store_true", help="Run full 3-track + v3.0 SAP/backtest/DAG simulation")
    parser.add_argument("--backtest", action="store_true", help="Run 30-day walk-forward regime stress backtest")
    parser.add_argument("--simulate-mainnet", action="store_true", help="Run live $0-spend Solana Mainnet v0+ALT simulateTransaction + MultiHopper program verification")
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
    if args.backtest:
        print(json.dumps(run_walk_forward_regime_backtest(DEFAULT_MANDATE), indent=2))
        return 0
    if args.simulate_mainnet:
        sim = simulate_solana_v0_dry_run(DEFAULT_MANDATE)
        mh_progs = verify_multihopper_programs_onchain()
        print(json.dumps({"v0_dry_run_simulation": sim, "multihopper_mainnet_programs": mh_progs}, indent=2))
        return 0

    print(json.dumps(run_demo(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
