"""
Unit & Property Invariant Suite for Steve Capital x OOBE SAP MCP x MultiHopper Agent.
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

from src.capital_engine import (  # noqa: E402
    SOLANA_MAX_PACKET_BYTES,
    MandatePolicy,
    MandateViolationError,
    compute_barbell_strategy,
    delegate_subagent_vault,
    detect_route_abuse,
    evaluate_mandate_action,
    plan_multihopper_route,
)
from src.mcp_server import DEFAULT_MANDATE, McpHttpHandler, handle_mcp_request  # noqa: E402


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
            vault_address="SubVaultIsolatedAddress111111111111111111111",
            allocated_budget_usd=200.0,
            max_single_tx_usd=100.0,
            allowed_protocols=["kamino", "meteora_dlmm"],
        )
        self.assertEqual(sub.allocated_budget_usd, 200.0)

        # Escalating protocol outside parent allowlist must raise MandateViolationError
        strict_parent = dataclasses.replace(self.policy, allowed_protocols=("kamino",))
        with self.assertRaises(MandateViolationError):
            delegate_subagent_vault(
                strict_parent,
                subagent_id="sub-02",
                role="Escalated Perp Bot",
                vault_address="SubVaultIsolatedAddress222222222222222222222",
                allocated_budget_usd=50.0,
                max_single_tx_usd=25.0,
                allowed_protocols=["kamino", "adrena"],
            )

        # Exceeding parent single-tx cap must raise MandateViolationError
        with self.assertRaises(MandateViolationError):
            delegate_subagent_vault(
                self.policy,
                subagent_id="sub-03",
                role="Oversized Tx Bot",
                vault_address="SubVaultIsolatedAddress333333333333333333333",
                allocated_budget_usd=100.0,
                max_single_tx_usd=250.0,  # parent max_single_tx_usd is 200.0
                allowed_protocols=["kamino"],
            )

    def test_07_barbell_strategy_conserves_exact_10000_bps(self) -> None:
        strat = compute_barbell_strategy(self.policy, dry_powder_floor_bps=1500)
        self.assertEqual(strat["total_weight_bps"], 10_000)
        self.assertEqual(sum(a["weight_bps"] for a in strat["allocations"]), 10_000)
        self.assertGreater(strat["weighted_expected_apr_bps"], 450)
        # Every volatile sleeve capped at <= 3000 bps
        for alloc in strat["allocations"]:
            if alloc["category"] not in ("yield", "reserve"):
                self.assertLessEqual(alloc["weight_bps"], 3000)

    def test_08_multihopper_counts_principal_once_and_fits_solana_v0_limit(self) -> None:
        route = plan_multihopper_route(
            self.policy,
            input_token="SOL",
            input_amount=1.0,  # $185 USD <= $200 max_single_tx_usd
            output_token="USDC",
            recipients=[
                {"wallet": "DestWalletAlpha111111111111111111111111111", "label": "Ops", "share_bps": 5000},
                {"wallet": "DestWalletBeta2222222222222222222222222222", "label": "SubVault", "share_bps": 3000},
                {"wallet": "DestWalletGamma333333333333333333333333333", "label": "Audit", "share_bps": 2000},
            ],
            intermediate_venues=("Raydium CLMM", "Meteora DLMM", "Orca Whirlpool"),
        )
        # Principal counted strictly ONCE ($185.00), NOT 3x across 3 hops or 3 recipients
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
                recipients=[{"wallet": "DestWalletAlpha111", "share_bps": 9000}],
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

        # JSON-RPC notification without `id` must return None (204 over HTTP)
        notif_resp = handle_mcp_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(notif_resp)

        tools_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("steve_evaluate_mandate", tool_names)
        self.assertIn("multihopper_plan_compliant_route", tool_names)

        # Tool error surfaces `isError: True` per MCP 2024-11-05
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

        # Verify live ephemeral HTTP server cleans up cleanly in finally block
        httpd = http.server.HTTPServer(("127.0.0.1", 0), McpHttpHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            health = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5).read())
            self.assertTrue(health["ok"])
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


if __name__ == "__main__":
    unittest.main()
