"""
Unit & Property Invariant Suite for Steve Capital x OOBE SAP MCP x MultiHopper x Ace Data Cloud Agent.
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import os
import sys
import threading
import unittest
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.arena_backtester import (
    DEFAULT_SPECIALIST_SPECS,
    RegimeEpoch,
    plan_agent_space_delegation_dag,
    run_walk_forward_regime_backtest,
)
from src.capital_engine import (
    MULTIHOPPER_CORE_PROGRAM_ID,
    SOLANA_MAX_PACKET_BYTES,
    MandateViolationError,
    compute_barbell_strategy,
    compute_multihopper_onchain_fees,
    delegate_subagent_vault,
    detect_route_abuse,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.launchpad_and_arena import (
    audit_steve_launchpad_manifest,
    build_x402_payment_challenge,
    score_verified_arena_xp_ledger,
    verify_x402_agent_payment_envelope,
)
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, handle_mcp_request
from src.partner_integrations import (
    plan_magicblock_private_settlement,
    synthesize_acedata_macro_brief,
    verify_acedata_side_track_ledger,
)
from src.sap_identity_and_sim import (
    SAP_EXPECTED_REGISTRATION_LAMPORTS,
    SAP_PROTOCOL_TREASURY,
    build_sap_agent_identity_passport,
    compile_v0_alt_transaction,
    decode_compact_u16,
    encode_compact_u16,
    inject_signature_at_slot,
    simulate_solana_v0_dry_run,
    verify_multihopper_programs_onchain,
    verify_sap_protocol_fee_invariant,
)
from src.solana_telemetry import (
    PYTH_PRICE_FEED_IDS,
    decode_base58_pubkey,
    fetch_pyth_hermes_quotes,
    inspect_solana_arena_wallet,
    is_valid_solana_pubkey,
)


class TestSteveCapitalAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = DEFAULT_MANDATE

    def test_01_mandate_approves_compliant_adrena_commodity_hedge(self) -> None:
        res = evaluate_mandate_action(
            self.policy,
            protocol="adrena",
            notional_usd=150.0,
            rolling_24h_spent_usd=100.0,
            current_drawdown_bps=120,
            estimated_slippage_bps=25,
            leverage=2.0,
            pyth_conf_bps=14,
            trm_risk_score=3,
        )
        self.assertTrue(res["approved"])
        self.assertEqual(res["violations"], [])
        self.assertTrue(res["verifiable_receipt"].startswith("steve:receipt:v1:"))
        self.assertAlmostEqual(res["remaining_24h_budget_usd"], 350.0)

    def test_02_mandate_blocks_underfunded_arena_wallet_below_20_usd(self) -> None:
        underfunded = dataclasses.replace(self.policy, funded_balance_usd=19.50)
        res = evaluate_mandate_action(underfunded, protocol="kamino", notional_usd=10.0)
        self.assertFalse(res["approved"])
        self.assertTrue(any("arena_funding_below_minimum" in v for v in res["violations"]))

    def test_03_mandate_blocks_24h_rolling_spend_and_drawdown_breaker(self) -> None:
        res = evaluate_mandate_action(
            self.policy,
            protocol="meteora_dlmm",
            notional_usd=180.0,
            rolling_24h_spent_usd=490.0,
            current_drawdown_bps=500,
        )
        self.assertFalse(res["approved"])
        self.assertTrue(any("exceeds_24h_spend_limit" in v for v in res["violations"]))
        self.assertTrue(any("drawdown_circuit_breaker_tripped" in v for v in res["violations"]))

    def test_04_mandate_blocks_wide_pyth_oracle_and_high_trm_risk(self) -> None:
        res = evaluate_mandate_action(
            self.policy,
            protocol="phoenix",
            notional_usd=50.0,
            pyth_conf_bps=65,
            trm_risk_score=70,
        )
        self.assertFalse(res["approved"])
        self.assertTrue(any("pyth_oracle_confidence_too_wide" in v for v in res["violations"]))
        self.assertTrue(any("trm_counterparty_risk_blocked" in v for v in res["violations"]))

    def test_05_anti_wash_blocks_self_transfer_and_circular_loops(self) -> None:
        abusive_self, reason_self = detect_route_abuse(
            "AgentWalletA",
            ["MeteoraPool1"],
            ["RecipientB", "AgentWalletA"],
        )
        self.assertTrue(abusive_self)
        self.assertIn("self_transfer_prohibited", str(reason_self))

        abusive_circle, reason_circle = detect_route_abuse(
            "AgentWalletA",
            ["PoolX", "PoolY", "PoolX"],
            ["RecipientB"],
        )
        self.assertTrue(abusive_circle)
        self.assertIn("circular_hop_detected", str(reason_circle))

    def test_06_subagent_delegation_enforces_monotone_privilege_containment(self) -> None:
        sub = delegate_subagent_vault(
            self.policy,
            subagent_id="sub-01",
            role="Kamino Yield Optimizer",
            vault_address="4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
            allocated_budget_usd=200.0,
            max_single_tx_usd=100.0,
            allowed_protocols=["kamino", "meteora_dlmm"],
        )
        self.assertEqual(sub.allocated_budget_usd, 200.0)

        strict_parent = dataclasses.replace(self.policy, allowed_protocols=("kamino",))
        with self.assertRaises(MandateViolationError):
            delegate_subagent_vault(
                strict_parent,
                subagent_id="sub-02",
                role="Escalated Perp Bot",
                vault_address="8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj",
                allocated_budget_usd=50.0,
                max_single_tx_usd=25.0,
                allowed_protocols=["kamino", "adrena"],
            )

        with self.assertRaises(MandateViolationError):
            delegate_subagent_vault(
                self.policy,
                subagent_id="sub-03",
                role="Oversized Tx Bot",
                vault_address="8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj",
                allocated_budget_usd=100.0,
                max_single_tx_usd=250.0,
                allowed_protocols=["kamino"],
            )

    def test_07_barbell_strategy_conserves_exact_10000_bps(self) -> None:
        strat = compute_barbell_strategy(self.policy, dry_powder_floor_bps=1500)
        self.assertEqual(strat["total_weight_bps"], 10_000)
        self.assertEqual(sum(a["weight_bps"] for a in strat["allocations"]), 10_000)
        self.assertGreater(strat["weighted_expected_apr_bps"], 450)
        for alloc in strat["allocations"]:
            if alloc["category"] not in ("yield", "reserve"):
                self.assertLessEqual(alloc["weight_bps"], 3000)

    def test_08_multihopper_counts_principal_once_and_fits_solana_v0_limit(self) -> None:
        route = plan_multihopper_route(
            self.policy,
            input_token="SOL",
            input_amount=1.0,
            output_token="USDC",
            recipients=[
                {"wallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "label": "Ops", "share_bps": 5000},
                {"wallet": "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj", "label": "SubVault", "share_bps": 3000},
                {"wallet": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "label": "Audit", "share_bps": 2000},
            ],
            intermediate_venues=("Raydium CLMM", "Meteora DLMM", "Orca Whirlpool"),
        )
        self.assertEqual(route["verified_routed_principal_usd"], 185.00)
        self.assertTrue(route["principal_counted_once"])
        self.assertLessEqual(
            route["solana_v0_packet"]["v0_compressed_bytes"],
            SOLANA_MAX_PACKET_BYTES,
        )
        self.assertLess(
            route["solana_v0_packet"]["v0_compressed_bytes"],
            route["solana_v0_packet"]["legacy_uncompressed_bytes"],
        )

    def test_09_multihopper_rejects_non_10000_bps_or_self_transfer(self) -> None:
        with self.assertRaises(ValueError):
            plan_multihopper_route(
                self.policy,
                input_token="USDC",
                input_amount=50.0,
                output_token="USDC",
                recipients=[{"wallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "share_bps": 9000}],
            )

        with self.assertRaises(MandateViolationError):
            plan_multihopper_route(
                self.policy,
                input_token="USDC",
                input_amount=50.0,
                output_token="USDC",
                recipients=[{"wallet": self.policy.agent_wallet, "share_bps": 10000}],
            )

    def test_10_mcp_jsonrpc_lifecycle_notifications_and_http_transport(self) -> None:
        init_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertIsNotNone(init_resp)
        self.assertEqual(init_resp["result"]["protocolVersion"], "2024-11-05")

        notif_resp = handle_mcp_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(notif_resp)

        tools_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertEqual(len(tool_names), 15)
        self.assertIn("steve_evaluate_mandate", tool_names)
        self.assertIn("multihopper_plan_compliant_route", tool_names)
        self.assertIn("acedata_macro_regime_brief", tool_names)
        self.assertIn("magicblock_plan_private_transfer", tool_names)
        self.assertIn("solana_inspect_arena_wallet", tool_names)
        self.assertIn("steve_backtest_barbell_regimes", tool_names)
        self.assertIn("steve_plan_agent_space_dag", tool_names)
        self.assertIn("sap_build_agent_identity_passport", tool_names)
        self.assertIn("solana_simulate_v0_dry_run", tool_names)
        self.assertIn("steve_audit_launchpad_token", tool_names)
        self.assertIn("steve_score_arena_xp_ledger", tool_names)
        self.assertIn("sap_verify_x402_payment", tool_names)

        err_call = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "multihopper_plan_compliant_route",
                    "arguments": {
                        "input_token": "USDC",
                        "input_amount": 50.0,
                        "recipients": [{"wallet": self.policy.agent_wallet, "share_bps": 10000}],
                    },
                },
            }
        )
        self.assertTrue(err_call["result"]["isError"])

        httpd = http.server.HTTPServer(("127.0.0.1", 0), McpHttpHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            health = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5).read())
            self.assertTrue(health["ok"])
            self.assertEqual(health["server"]["version"], "4.0.0")
            post_req = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "steve_compute_barbell_strategy", "arguments": {"funded_balance_usd": 250}},
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            post_resp = json.loads(urllib.request.urlopen(post_req, timeout=5).read())
            self.assertFalse(post_resp["result"]["isError"])
            self.assertEqual(post_resp["result"]["structuredContent"]["total_weight_bps"], 10_000)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_11_steve_kernel_mandate_schema_and_sap_streamable_http_2025_06_18(self) -> None:
        init_2025 = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(init_2025["result"]["protocolVersion"], "2025-06-18")

        mandate_call = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "steve_export_kernel_mandate",
                    "arguments": {"funded_balance_usd": 500.0, "approval_threshold_usd": 100.0},
                },
            }
        )
        self.assertFalse(mandate_call["result"]["isError"])
        kernel_mandate = mandate_call["result"]["structuredContent"]
        self.assertEqual(kernel_mandate["walletAddress"], self.policy.agent_wallet)
        self.assertEqual(kernel_mandate["limits"]["dailyBudget"]["period"], "utc-day")
        self.assertIn("kamino", kernel_mandate["limits"]["approvedProtocols"])
        self.assertIn("magicblock", kernel_mandate["limits"]["approvedProtocols"])
        self.assertTrue(kernel_mandate["limits"]["execution"]["requireStopLoss"])

        route = plan_multihopper_route(
            self.policy,
            input_token="USDC",
            input_amount=120.0,
            output_token="USDC",
            recipients=[
                {"wallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "label": "Ops", "share_bps": 6000},
                {"wallet": "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj", "label": "SubVault", "share_bps": 4000},
            ],
        )
        bplan = route["multihopper_broadcast_plan"]
        self.assertTrue(bplan["withinGroupCeiling"])
        self.assertEqual(bplan["groups"][0]["kind"], "orchestratorInit")
        self.assertEqual(bplan["groups"][0]["signingMode"], "partialSign")
        self.assertEqual(bplan["groups"][1]["txFormat"], "v0")
        self.assertEqual(bplan["relayEndpoint"], "/api/multihopper/broadcast")

    def test_12_solana_base58_pubkey_validation_strict_32_bytes(self) -> None:
        self.assertTrue(is_valid_solana_pubkey(self.policy.owner_wallet))
        self.assertTrue(is_valid_solana_pubkey(self.policy.agent_wallet))
        self.assertTrue(is_valid_solana_pubkey("11111111111111111111111111111111"))
        self.assertEqual(len(decode_base58_pubkey("11111111111111111111111111111111")), 32)

        # Invalid Base58 character '0' / 'O' / 'I' / 'l'
        self.assertFalse(is_valid_solana_pubkey("0WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"))
        # Too short
        self.assertFalse(is_valid_solana_pubkey("shortpubkey123"))

    def test_13_pyth_hermes_v2_scaling_and_staleness_guard(self) -> None:
        sol_id = PYTH_PRICE_FEED_IDS["SOL/USD"]
        mock_payload = {
            "parsed": [
                {
                    "id": sol_id,
                    "price": {
                        "price": "18645000000",
                        "conf": "14916000",
                        "expo": -8,
                        "publish_time": 1763210000,
                    },
                }
            ]
        }
        quotes = fetch_pyth_hermes_quotes(
            ("SOL/USD",),
            max_staleness_sec=120,
            now_unix=1763210045,
            http_get=lambda _u: mock_payload,
        )
        self.assertAlmostEqual(quotes["SOL/USD"]["price_usd"], 186.45, places=4)
        self.assertEqual(quotes["SOL/USD"]["conf_bps"], 8)
        self.assertEqual(quotes["SOL/USD"]["age_sec"], 45)

        # Stale feed beyond max_staleness_sec must fail closed
        with self.assertRaises(ValueError):
            fetch_pyth_hermes_quotes(
                ("SOL/USD",),
                max_staleness_sec=60,
                now_unix=1763210500,
                http_get=lambda _u: mock_payload,
            )

    def test_14_solana_arena_wallet_rpc_readiness_above_and_below_20_usd(self) -> None:
        def fake_rpc_funded(_url: str, body: dict) -> dict:
            if body["method"] == "getBalance":
                return {"result": {"value": 100_000_000}}  # 0.1 SOL
            return {
                "result": {
                    "value": [
                        {
                            "account": {
                                "data": {
                                    "parsed": {
                                        "info": {"tokenAmount": {"uiAmountString": "12.50"}}
                                    }
                                }
                            }
                        }
                    ]
                }
            }

        funded = inspect_solana_arena_wallet(
            self.policy.agent_wallet,
            sol_price_usd=185.0,
            rpc_post=fake_rpc_funded,
        )
        # 0.1 * 185 ($18.50) + $12.50 USDC = $31.00 >= $20.00
        self.assertTrue(funded["arena_eligible"])
        self.assertAlmostEqual(funded["total_arena_equity_usd"], 31.00, places=2)
        self.assertEqual(funded["shortfall_usd"], 0.0)
        self.assertTrue(funded["readiness_receipt"].startswith("steve:arena-check:v1:"))

        def fake_rpc_empty(_url: str, body: dict) -> dict:
            if body["method"] == "getBalance":
                return {"result": {"value": 20_000_000}}  # 0.02 SOL = $3.70
            return {"result": {"value": []}}

        underfunded = inspect_solana_arena_wallet(
            self.policy.agent_wallet,
            sol_price_usd=185.0,
            rpc_post=fake_rpc_empty,
        )
        self.assertFalse(underfunded["arena_eligible"])
        self.assertAlmostEqual(underfunded["shortfall_usd"], 16.30, places=2)

    def test_15_acedata_side_track_enforces_5_purchased_non_duplicate_requests(self) -> None:
        mixed_records = [
            # 4 valid purchased requests
            *[
                {
                    "request_id": f"paid-{i}",
                    "tool_name": "ace_deep_research",
                    "status": "succeeded",
                    "credit_source": "purchased",
                    "credits_spent": 0.4,
                    "query_fingerprint": f"unique-topic-{i}",
                    "timestamp_unix": 1763200000 + i,
                }
                for i in range(1, 5)
            ],
            # Excluded: free_trial credit source
            {
                "request_id": "trial-5",
                "tool_name": "ace_google_search",
                "status": "succeeded",
                "credit_source": "free_trial",
                "credits_spent": 0.2,
                "query_fingerprint": "unique-topic-5",
                "timestamp_unix": 1763200010,
            },
            # Excluded: duplicate query_fingerprint (artificial spam)
            {
                "request_id": "dup-6",
                "tool_name": "ace_google_search",
                "status": "succeeded",
                "credit_source": "purchased",
                "credits_spent": 0.2,
                "query_fingerprint": "unique-topic-1",
                "timestamp_unix": 1763200020,
            },
        ]
        audit_fail = verify_acedata_side_track_ledger(self.policy.agent_wallet, mixed_records)
        self.assertFalse(audit_fail["side_track_eligible"])
        self.assertEqual(audit_fail["qualifying_paid_requests"], 4)
        self.assertEqual(audit_fail["remaining_paid_requests_needed"], 1)
        self.assertEqual(len(audit_fail["excluded_requests"]), 2)

        # Adding 5th distinct purchased request unlocks eligibility
        mixed_records.append(
            {
                "request_id": "paid-5",
                "tool_name": "ace_tts_narrate",
                "status": "succeeded",
                "credit_source": "purchased",
                "credits_spent": 0.35,
                "query_fingerprint": "unique-narration-brief-5",
                "timestamp_unix": 1763200030,
            }
        )
        audit_ok = verify_acedata_side_track_ledger(self.policy.agent_wallet, mixed_records)
        self.assertTrue(audit_ok["side_track_eligible"])
        self.assertEqual(audit_ok["qualifying_paid_requests"], 5)
        self.assertAlmostEqual(audit_ok["total_purchased_credits_spent"], 1.95, places=4)

    def test_16_acedata_macro_brief_regime_transitions(self) -> None:
        # Wide Pyth oracle spread forces DEFENSIVE_DELEVERAGE (1.0x leverage, 35% dry powder)
        defensive = synthesize_acedata_macro_brief(
            self.policy,
            pyth_sol_conf_bps=55,  # > 30 bps ceiling
            pyth_xau_conf_bps=12,
        )
        self.assertEqual(defensive["regime"], "DEFENSIVE_DELEVERAGE")
        self.assertEqual(defensive["recommended_mandate_overrides"]["max_perp_leverage"], 1.0)
        self.assertEqual(defensive["recommended_mandate_overrides"]["dry_powder_floor_bps"], 3500)

        # Inflation shock with clean oracle triggers COMMODITY_INFLATION_HEDGE
        inflation = synthesize_acedata_macro_brief(self.policy, pyth_sol_conf_bps=8, pyth_xau_conf_bps=11)
        self.assertEqual(inflation["regime"], "COMMODITY_INFLATION_HEDGE")
        self.assertEqual(inflation["recommended_mandate_overrides"]["adrena_xau_hedge_tilt_bps"], 2500)

    def test_17_magicblock_private_settlement_enforces_ttl_and_pre_shield_trm(self) -> None:
        plan = plan_magicblock_private_settlement(
            self.policy,
            token="USDC",
            amount=95.0,
            recipient_wallet="4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
            session_ttl_seconds=600,
            trm_risk_score=4,
        )
        self.assertEqual(plan["status"], "PREPARED_EPHEMERAL_ROLLUP_DELEGATION")
        self.assertTrue(plan["pre_shield_compliance"]["trm_screened_before_shielding"])
        self.assertTrue(plan["magicblock_session_id"].startswith("mb:er-session:v1:"))

        # Excessive session TTL (> 3600s) blocked for least-privilege safety
        with self.assertRaises(MandateViolationError):
            plan_magicblock_private_settlement(
                self.policy,
                token="USDC",
                amount=50.0,
                recipient_wallet="4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
                session_ttl_seconds=7200,
            )

        # Self-transfer inside private Ephemeral Rollup still blocked!
        with self.assertRaises(MandateViolationError):
            plan_magicblock_private_settlement(
                self.policy,
                token="USDC",
                amount=50.0,
                recipient_wallet=self.policy.agent_wallet,
            )

    def test_18_mcp_tools_call_acedata_and_magicblock_and_workspace_resource(self) -> None:
        res_cfg = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "resources/read",
                "params": {"uri": "steve://mcp-workspace/config"},
            }
        )
        cfg_json = json.loads(res_cfg["result"]["contents"][0]["text"])
        self.assertIn("ace-mcp", cfg_json["mcpServers"])

        mb_call = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {
                    "name": "magicblock_plan_private_transfer",
                    "arguments": {
                        "token": "USDC",
                        "amount": 60.0,
                        "recipient_wallet": "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj",
                    },
                },
            }
        )
        self.assertFalse(mb_call["result"]["isError"])
        self.assertEqual(mb_call["result"]["structuredContent"]["protocol"], "magicblock")

    def test_19_hermes_401_falls_back_cleanly_to_coinbase_spot(self) -> None:
        import urllib.error

        def fake_rpc(_url: str, body: dict) -> dict:
            if body["method"] == "getBalance":
                return {"result": {"value": 500_000_000}}  # 0.5 SOL
            return {"result": {"value": []}}

        def fake_http_get(url: str) -> dict:
            if "pyth.network" in url:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
            return {"data": {"amount": "72.00", "base": "SOL", "currency": "USD"}}

        report = inspect_solana_arena_wallet(
            self.policy.agent_wallet,
            rpc_post=fake_rpc,
            http_get=fake_http_get,
        )
        self.assertEqual(report["price_source"], "coinbase_spot_fallback")
        self.assertAlmostEqual(report["total_arena_equity_usd"], 36.0, places=2)
        self.assertTrue(report["arena_eligible"])

    def test_20_walk_forward_backtest_outperforms_uncapped_and_obeys_drawdown_ceiling(self) -> None:
        bt = run_walk_forward_regime_backtest(self.policy)
        self.assertEqual(bt["horizon_days"], 30)
        self.assertTrue(bt["within_drawdown_mandate"])
        self.assertLess(
            bt["steve_pulse_barbell"]["max_drawdown_bps"],
            self.policy.max_portfolio_drawdown_bps,
        )
        self.assertGreater(bt["outperformance_vs_uncapped_bps"], 0)
        self.assertGreater(bt["drawdown_reduction_vs_uncapped_bps"], 100)
        self.assertEqual(bt["circuit_breaker_saves"], 6)
        self.assertEqual(bt["arena_xp_projection"]["verification_mode"], "simulated_pre_mainnet")
        self.assertTrue(bt["backtest_receipt"].startswith("steve:backtest:v2:"))

    def test_21_walk_forward_backtest_circuit_breaker_fires_on_wide_pyth_oracle(self) -> None:
        shock_epochs = [
            RegimeEpoch(
                day=1,
                regime="ORACLE_LATENCY_FLASH_SHOCK",
                pyth_max_conf_bps=55,
                sleeve_daily_returns_bps={
                    "kamino": 3.0,
                    "meteora_dlmm": -250.0,
                    "adrena": -180.0,
                    "phoenix": -210.0,
                },
            )
        ]
        bt = run_walk_forward_regime_backtest(self.policy, epochs=shock_epochs)
        self.assertEqual(bt["circuit_breaker_saves"], 1)
        self.assertEqual(bt["steve_pulse_barbell"]["max_drawdown_bps"], 0)
        self.assertGreater(bt["steve_pulse_barbell"]["net_return_bps"], -1)
        self.assertLess(bt["benchmarks"]["uncapped_equal_weight_defi"]["net_return_bps"], -150)

    def test_22_agent_space_dag_verifies_reserve_floor_vault_isolation_and_acyclicity(self) -> None:
        dag = plan_agent_space_delegation_dag(self.policy)
        self.assertTrue(dag["invariants_verified"]["reserve_floor_preserved"])
        self.assertTrue(dag["invariants_verified"]["pairwise_vault_isolation"])
        self.assertTrue(dag["invariants_verified"]["monotone_privilege_containment"])
        self.assertTrue(dag["invariants_verified"]["acyclic_settlement_dag"])
        self.assertEqual(len(dag["subagents"]), 3)
        self.assertAlmostEqual(dag["total_delegated_usd"] + dag["unallocated_parent_reserve_usd"], 500.0, places=2)
        self.assertTrue(dag["agent_space_receipt"].startswith("steve:agentspace:v2:"))

    def test_23_agent_space_dag_rejects_inter_agent_settlement_cycle(self) -> None:
        cyclic_edges = [
            ("subagent-kamino-reserve-01", "subagent-adrena-commodity-02"),
            ("subagent-adrena-commodity-02", "subagent-magicblock-settlement-03"),
            ("subagent-magicblock-settlement-03", "subagent-kamino-reserve-01"),
        ]
        with self.assertRaises(MandateViolationError):
            plan_agent_space_delegation_dag(self.policy, settlement_edges=cyclic_edges)

    def test_24_agent_space_dag_rejects_duplicate_or_parent_vault_reuse(self) -> None:
        dup_specs = [
            dict(DEFAULT_SPECIALIST_SPECS[0]),
            {**DEFAULT_SPECIALIST_SPECS[1], "vault_address": DEFAULT_SPECIALIST_SPECS[0]["vault_address"]},
        ]
        with self.assertRaises(MandateViolationError):
            plan_agent_space_delegation_dag(self.policy, specs=dup_specs)

        parent_reuse_specs = [
            {**DEFAULT_SPECIALIST_SPECS[0], "vault_address": self.policy.agent_wallet},
        ]
        with self.assertRaises(MandateViolationError):
            plan_agent_space_delegation_dag(self.policy, specs=parent_reuse_specs)

    def test_25_agent_space_dag_rejects_reserve_floor_breach(self) -> None:
        over_allocated = [
            {**DEFAULT_SPECIALIST_SPECS[0], "allocated_budget_usd": 250.0},
            {**DEFAULT_SPECIALIST_SPECS[1], "allocated_budget_usd": 200.0},
        ]
        # 250 + 200 = $450 > $425 max delegatable (15% reserve floor on $500)
        with self.assertRaises(MandateViolationError):
            plan_agent_space_delegation_dag(self.policy, specs=over_allocated, min_parent_reserve_bps=1500)

    def test_26_mcp_tools_call_v2_backtest_and_agent_space_dag(self) -> None:
        bt_resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {"name": "steve_backtest_barbell_regimes", "arguments": {"funded_balance_usd": 500.0}},
            }
        )
        self.assertFalse(bt_resp["result"]["isError"])
        self.assertTrue(bt_resp["result"]["structuredContent"]["within_drawdown_mandate"])

        dag_resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "steve_plan_agent_space_dag", "arguments": {"funded_balance_usd": 500.0}},
            }
        )
        self.assertFalse(dag_resp["result"]["isError"])
        self.assertEqual(len(dag_resp["result"]["structuredContent"]["subagents"]), 3)

    def test_27_cli_demo_and_backtest_entrypoints_emit_valid_json(self) -> None:
        import io
        from contextlib import redirect_stdout

        from src.cli import main as cli_main

        buf_demo = io.StringIO()
        with redirect_stdout(buf_demo):
            rc1 = cli_main(["--demo"])
        self.assertEqual(rc1, 0)
        demo_doc = json.loads(buf_demo.getvalue())
        self.assertEqual(demo_doc["version"], "4.0.0")
        self.assertIn("walk_forward_regime_backtest", demo_doc)
        self.assertIn("agent_space_delegation_dag", demo_doc)
        self.assertIn("sap_agent_identity_passport", demo_doc)
        self.assertIn("steve_launchpad_audit", demo_doc)
        self.assertIn("verified_arena_xp_ledger", demo_doc)
        self.assertIn("x402_agent_payment_verification", demo_doc)

        buf_bt = io.StringIO()
        with redirect_stdout(buf_bt):
            rc2 = cli_main(["--backtest"])
        self.assertEqual(rc2, 0)
        bt_doc = json.loads(buf_bt.getvalue())
        self.assertEqual(bt_doc["horizon_days"], 30)

    def test_28_sap_protocol_fee_invariant_fails_closed_on_underpayment(self) -> None:
        ok = verify_sap_protocol_fee_invariant(
            agent_account_exists=True,
            observed_treasury_lamports_delta=SAP_EXPECTED_REGISTRATION_LAMPORTS,
        )
        self.assertTrue(ok["success"])
        self.assertTrue(ok["protocolComplete"])
        self.assertEqual(ok["protocolFee"]["status"], "verified")
        self.assertEqual(ok["protocolFee"]["expectedTreasury"], SAP_PROTOCOL_TREASURY)

        underpaid = verify_sap_protocol_fee_invariant(
            agent_account_exists=True,
            observed_treasury_lamports_delta=50_000_000,  # 0.05 SOL < 0.1 SOL
        )
        self.assertFalse(underpaid["success"])
        self.assertTrue(underpaid["agentRegistered"])
        self.assertFalse(underpaid["protocolComplete"])
        self.assertEqual(underpaid["protocolFee"]["status"], "missing_or_underpaid")

    def test_29_sap_identity_passport_enforces_https_uris_and_sns_domain(self) -> None:
        passport = build_sap_agent_identity_passport(self.policy)
        self.assertTrue(passport["protocol_fee_audit"]["protocolComplete"])
        self.assertFalse(passport["local_signer_bridge"]["hosted_custody"])
        self.assertEqual(
            passport["metaplex_mpl_core_metadata"]["sns"]["domain"],
            "stevepulse.sol",
        )
        self.assertTrue(passport["passport_receipt"].startswith("sap:passport:v2:"))

        # Local desktop file paths must be rejected per OOBE SAP MCP specification
        with self.assertRaises(MandateViolationError):
            build_sap_agent_identity_passport(
                self.policy,
                metadata_uri="/home/user/desktop/agent.json",
            )
        with self.assertRaises(MandateViolationError):
            build_sap_agent_identity_passport(
                self.policy,
                sns_domain="invalid-domain.eth",
            )

    def test_30_compact_u16_roundtrip_and_binary_v0_alt_compiler(self) -> None:
        for val in (0, 1, 127, 128, 255, 16383, 16384, 65535):
            enc = encode_compact_u16(val)
            dec, nxt = decode_compact_u16(enc, 0)
            self.assertEqual(dec, val)
            self.assertEqual(nxt, len(enc))

        compiled = compile_v0_alt_transaction(
            fee_payer=self.policy.agent_wallet,
            memo_text="StevePulse-v3:TestMemo",
            compute_unit_limit=250_000,
            alt_readonly_indexes=(0, 2, 3, 4),
        )
        self.assertEqual(compiled["version"], 0)
        self.assertTrue(compiled["fits_solana_1232b_limit"])
        self.assertLess(compiled["v0_serialized_bytes"], compiled["legacy_equivalent_bytes"])

        import base64

        raw = base64.b64decode(compiled["base64_tx"])
        sig_cnt, msg_offset = decode_compact_u16(raw, 0)
        self.assertEqual(sig_cnt, 1)
        # Byte immediately following signature array must be 0x80 (VersionedMessageV0 prefix)
        self.assertEqual(raw[msg_offset + 64], 0x80)

    def test_31_slot_preserving_signature_injection_preserves_ephemeral_sigs(self) -> None:
        import base64

        # Simulate a 2-signer v0 tx where slot 1 already holds a MultiHopper ephemeral signature
        msg_body = b"\x80\x02\x00\x01" + (b"\x11" * 96)
        ephemeral_sig = b"\xaa" * 64
        two_sig_raw = encode_compact_u16(2) + (b"\x00" * 64) + ephemeral_sig + msg_body
        b64_in = base64.b64encode(two_sig_raw).decode("ascii")

        agent_sig = b"\xbb" * 64
        b64_signed = inject_signature_at_slot(b64_in, slot_index=0, signature_64_bytes=agent_sig)
        decoded = base64.b64decode(b64_signed)
        _, off = decode_compact_u16(decoded, 0)
        self.assertEqual(decoded[off : off + 64], agent_sig)
        self.assertEqual(decoded[off + 64 : off + 128], ephemeral_sig)

    def test_32_multihopper_10_tier_fees_and_two_phase_confirm_broadcast(self) -> None:
        tier0 = compute_multihopper_onchain_fees(45.0, hops=3, destination_count=1)
        self.assertEqual(tier0["tierIndex"], 0)
        self.assertEqual(tier0["perHopFlatLamports"], 0)
        self.assertEqual(tier0["integratorShareBps"], 25)

        tier9 = compute_multihopper_onchain_fees(1200.0, hops=5, destination_count=4)
        self.assertEqual(tier9["tierIndex"], 9)
        self.assertEqual(tier9["perHopFlatLamports"], 2_000_000)
        self.assertEqual(tier9["totalFlatFeeLamports"], 10_000_000)
        self.assertEqual(tier9["integratorPercentShareUsd"], 3.0)  # 0.25% of $1,200

        route = plan_multihopper_route(
            self.policy,
            input_token="USDC",
            input_amount=150.0,
            output_token="USDC",
            recipients=[
                {"wallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "share_bps": 6000},
                {"wallet": "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj", "share_bps": 4000},
            ],
        )
        self.assertEqual(route["multihopper_programs"]["core"], MULTIHOPPER_CORE_PROGRAM_ID)
        flow = route["multihopper_v1_agentic_flow"]
        self.assertTrue(flow["twoPhaseConfirmBroadcast"])
        self.assertEqual(flow["strictBroadcastOrder"][0]["group"], "keeperFundingTx")
        self.assertEqual(flow["strictBroadcastOrder"][-1]["group"], "dispersionInitTxs")

    def test_33_multihopper_rejects_over_20_destinations_mh_017(self) -> None:
        too_many = [
            {"wallet": f"111111111111111111111111111111{i:02d}", "share_bps": 476}
            for i in range(21)
        ]
        too_many[0]["share_bps"] += 10_000 - sum(x["share_bps"] for x in too_many)
        with self.assertRaises(MandateViolationError):
            plan_multihopper_route(
                self.policy,
                input_token="USDC",
                input_amount=100.0,
                output_token="USDC",
                recipients=too_many,
            )

    def test_34_solana_v0_dry_run_simulation_mock_and_mcp_tools(self) -> None:
        def fake_sim_rpc(_url: str, body: dict) -> dict:
            self.assertEqual(body["method"], "simulateTransaction")
            return {
                "result": {
                    "context": {"slot": 471375999},
                    "value": {
                        "err": None,
                        "unitsConsumed": 27527,
                        "loadedAddresses": {"readonly": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"], "writable": []},
                        "logs": ["Program MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr success"],
                    },
                }
            }

        sim = simulate_solana_v0_dry_run(self.policy, rpc_post=fake_sim_rpc)
        self.assertTrue(sim["succeeded"])
        self.assertEqual(sim["units_consumed"], 27527)
        self.assertEqual(sim["simulation_source"], "solana_rpc_live")
        self.assertTrue(sim["simulation_receipt"].startswith("steve:sim:v3:"))

        progs = verify_multihopper_programs_onchain(
            rpc_post=lambda _u, _b: {
                "result": {
                    "context": {"slot": 471376000},
                    "value": [{"executable": True}, {"executable": True}, {"executable": True}],
                }
            }
        )
        self.assertTrue(progs["all_executable"])

        mcp_sim = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {
                    "name": "sap_build_agent_identity_passport",
                    "arguments": {"sns_domain": "stevepulse.sol"},
                },
            }
        )
        self.assertFalse(mcp_sim["result"]["isError"])
        self.assertTrue(
            mcp_sim["result"]["structuredContent"]["protocol_fee_audit"]["protocolComplete"]
        )

    def test_35_launchpad_approves_clean_manifest_and_conserves_10000_bps(self) -> None:
        res = audit_steve_launchpad_manifest(
            self.policy,
            token_name="StevePulse Vault Index",
            token_symbol="SPULSE",
            metadata_uri="https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json",
            initial_liquidity_usdc=120.0,
            creator_allocation_bps=1200,
        )
        self.assertTrue(res["approved"])
        self.assertEqual(res["violations"], [])
        self.assertTrue(res["security_invariants"]["supply_bps_conserved"])
        self.assertEqual(res["token_spec"]["bonding_curve_public_bps"], 8800)

    def test_36_launchpad_blocks_retained_authorities_and_insider_concentration(self) -> None:
        res = audit_steve_launchpad_manifest(
            self.policy,
            token_name="RugToken",
            token_symbol="RUG",
            metadata_uri="file:///Users/local/rug.json",
            initial_liquidity_usdc=350.0,  # exceeds $200 single-tx mandate
            creator_allocation_bps=3500,   # exceeds 20% insider cap
            mint_authority_revoked=False,
            freeze_authority_revoked=False,
            token2022_transfer_fee_bps=500,
        )
        self.assertFalse(res["approved"])
        joined = " | ".join(res["violations"])
        self.assertIn("mint_authority_must_be_revoked", joined)
        self.assertIn("freeze_authority_must_be_revoked", joined)
        self.assertIn("insider_allocation_exceeds_2000_bps", joined)
        self.assertIn("metadata_uri_must_be_public", joined)
        self.assertIn("initial_liquidity_exceeds_mandate_single_tx", joined)
        self.assertIn("token2022_transfer_fee_exceeds_250_bps", joined)

    def test_37_arena_xp_ledger_credits_diverse_valid_actions_with_bonus(self) -> None:
        events = [
            {"tx_signature": "sig-1", "category": "strategy_publish", "finalized_onchain": True},
            {"tx_signature": "sig-2", "category": "multihopper_mainnet_route", "principal_usd": 140.0, "finalized_onchain": True},
            {"tx_signature": "sig-3", "category": "subagent_delegation", "finalized_onchain": True},
            {"tx_signature": "sig-4", "category": "acedata_paid_brief", "finalized_onchain": True},
        ]
        res = score_verified_arena_xp_ledger(self.policy, events)
        self.assertTrue(res["arena_eligible"])
        self.assertEqual(res["credited_count"], 4)
        self.assertEqual(res["ecosystem_diversity_bonus_xp"], 100)
        self.assertEqual(res["verified_multihopper_principal_usd"], 140.0)
        self.assertEqual(res["total_verified_arena_xp"], 120 + 180 + 140 + 150 + 100)

    def test_38_arena_xp_ledger_excludes_duplicates_self_transfers_and_circular_volume(self) -> None:
        events = [
            {"tx_signature": "sig-ok", "category": "multihopper_mainnet_route", "principal_usd": 90.0, "finalized_onchain": True},
            {"tx_signature": "sig-ok", "category": "multihopper_mainnet_route", "principal_usd": 90.0, "finalized_onchain": True},
            {"tx_signature": "sig-self", "category": "multihopper_mainnet_route", "self_transfer": True, "principal_usd": 500.0, "finalized_onchain": True},
            {"tx_signature": "sig-circ", "category": "multihopper_mainnet_route", "circular_route": True, "principal_usd": 500.0, "finalized_onchain": True},
            {"tx_signature": "sig-unfin", "category": "strategy_publish", "finalized_onchain": False},
        ]
        res = score_verified_arena_xp_ledger(self.policy, events)
        self.assertEqual(res["credited_count"], 1)
        self.assertEqual(res["excluded_count"], 4)
        self.assertEqual(res["verified_multihopper_principal_usd"], 90.0)

    def test_39_arena_xp_ledger_enforces_20_usd_floor_and_anti_spam_cap(self) -> None:
        under = dataclasses.replace(self.policy, funded_balance_usd=15.0)
        res_under = score_verified_arena_xp_ledger(
            under,
            [{"tx_signature": "sig-a", "category": "strategy_publish", "finalized_onchain": True}],
        )
        self.assertFalse(res_under["arena_eligible"])
        self.assertEqual(res_under["total_verified_arena_xp"], 0)

        spam = [
            {"tx_signature": f"sig-spam-{i}", "category": "strategy_publish", "finalized_onchain": True}
            for i in range(11)
        ]
        res_spam = score_verified_arena_xp_ledger(self.policy, spam)
        self.assertEqual(res_spam["credited_count"], 8)
        self.assertEqual(res_spam["excluded_count"], 3)

    def test_40_x402_payment_challenge_and_valid_envelope_unlock_200(self) -> None:
        chal = build_x402_payment_challenge(self.policy, price_micro_usdc=1500, nonce="n-42")
        self.assertEqual(chal["http_status"], 402)
        ver = verify_x402_agent_payment_envelope(
            self.policy,
            chal,
            {
                "payerWallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
                "payTo": self.policy.agent_wallet,
                "assetMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "amountMicroUsdc": 1500,
                "nonce": "n-42",
                "txSignature": "5xValidSolanaSignature11111111111111111111111111",
                "trmRiskScore": 2,
            },
        )
        self.assertTrue(ver["verified"])
        self.assertEqual(ver["http_status_unlocked"], 200)
        self.assertEqual(ver["settledMicroUsdc"], 1500)

    def test_41_x402_blocks_replay_nonce_underpayment_self_pay_and_expiry(self) -> None:
        chal = build_x402_payment_challenge(
            self.policy,
            price_micro_usdc=2000,
            nonce="replayed-nonce",
            expires_at_unix=1_790_000_000,
        )
        ver = verify_x402_agent_payment_envelope(
            self.policy,
            chal,
            {
                "payerWallet": self.policy.agent_wallet,  # self-payment prohibited
                "payTo": self.policy.agent_wallet,
                "assetMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "amountMicroUsdc": 500,                   # underpaid
                "nonce": "replayed-nonce",
                "txSignature": "5xReplaySig111111111111111111111111111111111111",
                "trmRiskScore": 80,                       # high TRM risk
            },
            current_unix=1_795_300_000,
            consumed_nonces=["replayed-nonce"],
        )
        self.assertFalse(ver["verified"])
        self.assertEqual(ver["http_status_unlocked"], 402)
        joined = " | ".join(ver["violations"])
        self.assertIn("self_payment_prohibited", joined)
        self.assertIn("underpaid_x402_amount", joined)
        self.assertIn("replay_detected", joined)
        self.assertIn("challenge_expired", joined)
        self.assertIn("trm_counterparty_risk_exceeded", joined)

    def test_42_mcp_prompts_list_and_get_lifecycle(self) -> None:
        plist = handle_mcp_request({"jsonrpc": "2.0", "id": 50, "method": "prompts/list"})
        names = {p["name"] for p in plist["result"]["prompts"]}
        self.assertEqual(
            names,
            {"autonomous-rebalance-cycle", "multihopper-treasury-disbursement", "launchpad-due-diligence"},
        )

        pget = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 51,
                "method": "prompts/get",
                "params": {"name": "autonomous-rebalance-cycle", "arguments": {}},
            }
        )
        self.assertEqual(pget["result"]["messages"][0]["role"], "user")

        perr = handle_mcp_request(
            {"jsonrpc": "2.0", "id": 52, "method": "prompts/get", "params": {"name": "nonexistent"}}
        )
        self.assertEqual(perr["error"]["code"], -32602)

    def test_43_mcp_tool_call_launchpad_audit(self) -> None:
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 53,
                "method": "tools/call",
                "params": {
                    "name": "steve_audit_launchpad_token",
                    "arguments": {
                        "token_name": "StevePulse Index",
                        "token_symbol": "SPULSE",
                        "metadata_uri": "https://jeffrey-graham.github.io/steve-capital-solana-agent/agent-metadata.json",
                        "initial_liquidity_usdc": 100.0,
                    },
                },
            }
        )
        self.assertFalse(resp["result"]["isError"])
        self.assertTrue(resp["result"]["structuredContent"]["approved"])

    def test_44_mcp_tool_call_arena_xp_ledger(self) -> None:
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 54,
                "method": "tools/call",
                "params": {
                    "name": "steve_score_arena_xp_ledger",
                    "arguments": {
                        "activities": [
                            {"tx_signature": "sig-mcp-1", "category": "strategy_publish", "finalized_onchain": True}
                        ]
                    },
                },
            }
        )
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(resp["result"]["structuredContent"]["total_verified_arena_xp"], 120)

    def test_45_mcp_tool_call_x402_verification(self) -> None:
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 55,
                "method": "tools/call",
                "params": {
                    "name": "sap_verify_x402_payment",
                    "arguments": {
                        "nonce": "mcp-nonce-1",
                        "payment_envelope": {
                            "payerWallet": "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T",
                            "payTo": self.policy.agent_wallet,
                            "assetMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                            "amountMicroUsdc": 1000,
                            "nonce": "mcp-nonce-1",
                            "txSignature": "5xMcpX402Sig1111111111111111111111111111111111",
                        },
                    },
                },
            }
        )
        self.assertFalse(resp["result"]["isError"])
        self.assertTrue(resp["result"]["structuredContent"]["verification"]["verified"])

    def test_46_http_cors_options_and_static_manifests_valid(self) -> None:
        with open(os.path.join(ROOT_DIR, ".well-known", "x402.json"), encoding="utf-8") as f:
            x402_doc = json.load(f)
        self.assertEqual(x402_doc["x402Version"], 1)
        self.assertTrue(os.path.exists(os.path.join(ROOT_DIR, "og.png")))
        self.assertTrue(os.path.exists(os.path.join(ROOT_DIR, ".nojekyll")))

        httpd = http.server.HTTPServer(("127.0.0.1", 0), McpHttpHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            opt_req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", method="OPTIONS")
            with urllib.request.urlopen(opt_req, timeout=5) as resp:
                self.assertEqual(resp.status, 204)
                self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
