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

from src.capital_engine import (
    SOLANA_MAX_PACKET_BYTES,
    MandateViolationError,
    compute_barbell_strategy,
    delegate_subagent_vault,
    detect_route_abuse,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, handle_mcp_request
from src.partner_integrations import (
    plan_magicblock_private_settlement,
    synthesize_acedata_macro_brief,
    verify_acedata_side_track_ledger,
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
        self.assertEqual(len(tool_names), 8)
        self.assertIn("steve_evaluate_mandate", tool_names)
        self.assertIn("multihopper_plan_compliant_route", tool_names)
        self.assertIn("acedata_macro_regime_brief", tool_names)
        self.assertIn("magicblock_plan_private_transfer", tool_names)
        self.assertIn("solana_inspect_arena_wallet", tool_names)

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
            self.assertEqual(health["server"]["version"], "1.2.0")
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


if __name__ == "__main__":
    unittest.main()
