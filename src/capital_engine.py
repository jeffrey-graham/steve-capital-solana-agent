"""
Steve Capital Autonomous Capital Engine & MultiHopper Programmable Router
=========================================================================
Implements programmable risk guardrails, Pyth-confidence-gated fractional Kelly
barbell allocation across Solana DeFi & Adrena synthetic commodities (XAU/XAG/WTI),
sub-agent vault delegation with strict privilege-containment invariants, and
MultiHopper non-custodial routing with anti-wash/circularity verification and
Solana v0 + Address Lookup Table (ALT) packet-budget validation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any

SOLANA_MAX_PACKET_BYTES = 1232
STEVE_MIN_ARENA_FUNDING_USD = 20.0

MULTIHOPPER_CORE_PROGRAM_ID = "3jLoS2wbNgtKzieUUxwg6Xhdv6gbZkHDtPWA9ZAgspFh"
MULTIHOPPER_ORCHESTRATOR_PROGRAM_ID = "4TPCmR2uN3hDM1FbTsf7ZtFXwXGSz4u1Kxv5YHj6eruX"
MULTIHOPPER_TRANSFER_HOOK_PROGRAM_ID = "2JEv3pD6nczEvn1xDXaEzehkJofPPjoQQpnW5nGY3r52"

# Official MultiHopper Mainnet 10-Tier Per-Hop Lamport Schedule (dev-docs.multihopper.com/concepts/pricing)
MULTIHOPPER_FEE_TIERS_USD_LAMPORTS: tuple[tuple[float, int], ...] = (
    (50.00, 0),
    (106.25, 125_000),
    (162.50, 375_000),
    (218.75, 625_000),
    (275.00, 875_000),
    (331.25, 1_125_000),
    (387.50, 1_375_000),
    (443.75, 1_625_000),
    (500.00, 1_875_000),
)
MULTIHOPPER_TOP_TIER_LAMPORTS_PER_HOP = 2_000_000
MULTIHOPPER_PERCENT_FEE_BPS = 50  # 0.50% total; 50/50 split -> 25 bps atomic integrator share
MULTIHOPPER_TRM_SCREENING_LAMPORTS_PER_WALLET = 2_000_000  # 0.002 SOL per screened wallet

SUPPORTED_ECOSYSTEM_PROTOCOLS = frozenset(
    {
        "kamino",
        "meteora_dlmm",
        "raydium_clmm",
        "orca_whirlpool",
        "jupiter",
        "sunrise",
        "adrena",
        "phoenix",
        "magicblock",
        "metaplex",
        "sns",
        "multihopper",
    }
)

ADRENA_SYNTHETIC_MARKETS = frozenset({"SOL-PERP", "XAU-PERP", "XAG-PERP", "WTI-PERP"})

TOKEN_USD_REFERENCE: dict[str, float] = {
    "USDC": 1.00,
    "USDT": 1.00,
    "USDG": 1.00,
    "SOL": 185.00,
    "JitoSOL": 211.50,
    "JUP": 1.12,
}


class MandateViolationError(ValueError):
    """Raised when an agent or sub-agent action violates its programmable mandate."""


@dataclasses.dataclass(frozen=True)
class MandatePolicy:
    mandate_id: str
    owner_wallet: str
    agent_wallet: str
    funded_balance_usd: float
    max_single_tx_usd: float = 250.0
    max_rolling_24h_spend_usd: float = 1000.0
    max_slippage_bps: int = 75
    max_portfolio_drawdown_bps: int = 600
    max_perp_leverage: float = 3.0
    max_pyth_conf_bps: int = 35
    allowed_protocols: tuple[str, ...] = (
        "kamino",
        "meteora_dlmm",
        "raydium_clmm",
        "orca_whirlpool",
        "jupiter",
        "adrena",
        "phoenix",
        "magicblock",
        "multihopper",
    )
    require_trm_screening: bool = True
    max_trm_risk_score: int = 25

    def policy_digest(self) -> str:
        canonical = json.dumps(dataclasses.asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_steve_kernel_mandate(
        self,
        *,
        objective: str = "Quarter-Kelly Barbell Yield, Commodity Basis & MultiHopper Settlement",
        statement: str = (
            "Allocate USDC/SOL across audited Solana DeFi vaults and synthetic commodity perps "
            "with strict Pyth confidence gates, TRM screening, and non-custodial MultiHopper routing."
        ),
        usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        approval_threshold_usd: float | None = None,
        min_liquidity_pct: int = 15,
        max_protocol_exposure_pct: int = 35,
    ) -> dict[str, Any]:
        """
        Exports a schema-exact Steve Capital Kernel Mandate object compatible with
        `agent.prepare_mandate` / `agent.validate_mandate` on `steve.oobeprotocol.ai`.
        """
        steve_registry_map = {
            "kamino": "kamino",
            "jupiter": "jupiter",
            "phoenix": "phoenix",
            "meteora_dlmm": "meteora",
            "raydium_clmm": "raydium",
            "orca_whirlpool": "orca",
            "adrena": "adrena",
            "magicblock": "magicblock",
            "multihopper": "multihopper",
        }
        approved_protocols = sorted(
            {steve_registry_map[p] for p in self.allowed_protocols if p in steve_registry_map}
        )
        threshold = (
            round(self.max_single_tx_usd * 0.5, 2)
            if approval_threshold_usd is None
            else round(approval_threshold_usd, 2)
        )
        drawdown_pct = max(1, min(100, round(self.max_portfolio_drawdown_bps / 100)))
        return {
            "walletAddress": self.agent_wallet,
            "objective": objective[:100],
            "statement": statement[:600],
            "capital": [
                {
                    "mint": usdc_mint,
                    "symbol": "USDC",
                    "amount": round(self.funded_balance_usd, 2),
                }
            ],
            "limits": {
                "maxTxSizeUsd": round(self.max_single_tx_usd, 2),
                "approvalThresholdUsd": threshold,
                "dailyBudget": {
                    "period": "utc-day",
                    "assets": [
                        {
                            "mint": usdc_mint,
                            "symbol": "USDC",
                            "amount": round(self.max_rolling_24h_spend_usd, 2),
                        }
                    ],
                },
                "maxProtocolExposurePct": max(1, min(100, max_protocol_exposure_pct)),
                "minLiquidityPct": max(0, min(100, min_liquidity_pct)),
                "approvedProtocols": approved_protocols,
                "drawdownLimitPct": drawdown_pct,
                "leverage": "none" if self.max_perp_leverage <= 1.0 else round(self.max_perp_leverage, 2),
                "execution": {
                    "actions": ["deposit", "withdraw", "swap", "hedge", "route_transfer", "private_transfer"],
                    "tools": [
                        "steve_evaluate_mandate",
                        "steve_compute_barbell_strategy",
                        "steve_delegate_subagent_vault",
                        "multihopper_plan_compliant_route",
                        "steve_export_kernel_mandate",
                        "solana_inspect_arena_wallet",
                        "acedata_macro_regime_brief",
                        "magicblock_plan_private_transfer",
                        "steve_backtest_barbell_regimes",
                        "steve_plan_agent_space_dag",
                        "sap_build_agent_identity_passport",
                        "solana_simulate_v0_dry_run",
                    ],
                    "markets": ["SOL/USDC", "USDC", "XAU-PERP", "WTI-PERP"],
                    "maxPositionNotionalUsd": round(self.funded_balance_usd * (max_protocol_exposure_pct / 100.0), 2),
                    "stopLossPct": max(1, min(100, round(drawdown_pct * 0.6))),
                    "requireStopLoss": True,
                    "forbidAddingToLosingPositions": True,
                    "unresolvedRules": [],
                },
            },
            "version": 1,
            "status": "active",
            "policyDigest": self.policy_digest(),
        }


@dataclasses.dataclass(frozen=True)
class SubAgentDelegation:
    subagent_id: str
    role: str
    parent_mandate_id: str
    vault_address: str
    allocated_budget_usd: float
    max_single_tx_usd: float
    allowed_protocols: tuple[str, ...]
    auto_revoke_drawdown_bps: int
    expires_at_unix: int


@dataclasses.dataclass(frozen=True)
class MarketOpportunity:
    venue: str
    protocol: str
    asset_pair: str
    category: str  # "yield", "spot_lp", "perp_commodity", "perp_crypto"
    expected_net_apr_bps: int
    annualized_volatility_bps: int
    pyth_conf_bps: int
    liquidity_depth_usd: float


DEFAULT_MARKET_SNAPSHOT: list[MarketOpportunity] = [
    MarketOpportunity(
        venue="Kamino Main Vault",
        protocol="kamino",
        asset_pair="USDC",
        category="yield",
        expected_net_apr_bps=940,
        annualized_volatility_bps=120,
        pyth_conf_bps=4,
        liquidity_depth_usd=185_000_000.0,
    ),
    MarketOpportunity(
        venue="Meteora Dynamic Fee Bin",
        protocol="meteora_dlmm",
        asset_pair="SOL/USDC",
        category="spot_lp",
        expected_net_apr_bps=2480,
        annualized_volatility_bps=2850,
        pyth_conf_bps=9,
        liquidity_depth_usd=42_000_000.0,
    ),
    MarketOpportunity(
        venue="Adrena Synthetic Gold Basis",
        protocol="adrena",
        asset_pair="XAU-PERP",
        category="perp_commodity",
        expected_net_apr_bps=1820,
        annualized_volatility_bps=1450,
        pyth_conf_bps=12,
        liquidity_depth_usd=14_500_000.0,
    ),
    MarketOpportunity(
        venue="Adrena Crude Oil Momentum Hedge",
        protocol="adrena",
        asset_pair="WTI-PERP",
        category="perp_commodity",
        expected_net_apr_bps=2150,
        annualized_volatility_bps=2600,
        pyth_conf_bps=18,
        liquidity_depth_usd=9_200_000.0,
    ),
    MarketOpportunity(
        venue="Phoenix Orderbook Maker Carry",
        protocol="phoenix",
        asset_pair="SOL/USDC",
        category="perp_crypto",
        expected_net_apr_bps=1690,
        annualized_volatility_bps=2100,
        pyth_conf_bps=8,
        liquidity_depth_usd=28_000_000.0,
    ),
]


def detect_route_abuse(
    origin_wallet: str,
    hop_wallets_or_pools: Sequence[str],
    destination_wallets: Sequence[str],
) -> tuple[bool, str | None]:
    """
    Detects prohibited wash-trading, self-transfers, and circular A->B->A flows
    in accordance with Steve Capital Arena and MultiHopper anti-abuse rules.
    """
    origin_norm = origin_wallet.strip()
    if not origin_norm:
        return True, "empty_origin_wallet"
    if not destination_wallets:
        return True, "empty_destination_wallets"

    seen_dests: set[str] = set()
    for dest in destination_wallets:
        d_norm = dest.strip()
        if not d_norm:
            return True, "blank_destination_wallet"
        if d_norm == origin_norm:
            return True, f"self_transfer_prohibited:{d_norm}"
        if d_norm in seen_dests:
            return True, f"duplicate_recipient_split:{d_norm}"
        seen_dests.add(d_norm)

    visited_nodes: list[str] = [origin_norm]
    for hop in hop_wallets_or_pools:
        h_norm = hop.strip()
        if not h_norm:
            return True, "blank_intermediate_hop"
        if h_norm in visited_nodes:
            return True, f"circular_hop_detected:{h_norm}"
        visited_nodes.append(h_norm)

    for dest in seen_dests:
        if dest in visited_nodes:
            return True, f"circular_destination_loop:{dest}"

    return False, None


def evaluate_mandate_action(
    policy: MandatePolicy,
    *,
    protocol: str,
    notional_usd: float,
    rolling_24h_spent_usd: float = 0.0,
    current_drawdown_bps: int = 0,
    estimated_slippage_bps: int = 15,
    leverage: float = 1.0,
    pyth_conf_bps: int = 8,
    trm_risk_score: int = 0,
    destination_wallets: Sequence[str] | None = None,
    intermediate_hops: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Evaluates a candidate autonomous execution against a Steve Capital MandatePolicy.
    Returns a structured decision record and verifiable SHA-256 receipt.
    """
    violations: list[str] = []
    proto = protocol.strip().lower()

    if policy.funded_balance_usd < STEVE_MIN_ARENA_FUNDING_USD:
        violations.append(
            f"arena_funding_below_minimum:{policy.funded_balance_usd:.2f}<{STEVE_MIN_ARENA_FUNDING_USD:.2f}"
        )
    if notional_usd <= 0 or math.isnan(notional_usd) or math.isinf(notional_usd):
        violations.append("invalid_notional_usd")
    if proto not in SUPPORTED_ECOSYSTEM_PROTOCOLS:
        violations.append(f"unsupported_ecosystem_protocol:{proto}")
    if proto not in {p.lower() for p in policy.allowed_protocols}:
        violations.append(f"protocol_not_in_mandate_allowlist:{proto}")
    if notional_usd > policy.max_single_tx_usd:
        violations.append(
            f"exceeds_single_tx_limit:{notional_usd:.2f}>{policy.max_single_tx_usd:.2f}"
        )
    if rolling_24h_spent_usd + notional_usd > policy.max_rolling_24h_spend_usd:
        violations.append(
            f"exceeds_24h_spend_limit:{rolling_24h_spent_usd + notional_usd:.2f}>{policy.max_rolling_24h_spend_usd:.2f}"
        )
    if current_drawdown_bps >= policy.max_portfolio_drawdown_bps:
        violations.append(
            f"drawdown_circuit_breaker_tripped:{current_drawdown_bps}>={policy.max_portfolio_drawdown_bps}"
        )
    if estimated_slippage_bps > policy.max_slippage_bps:
        violations.append(
            f"slippage_exceeds_guardrail:{estimated_slippage_bps}>{policy.max_slippage_bps}"
        )
    if leverage > policy.max_perp_leverage:
        violations.append(
            f"leverage_exceeds_mandate:{leverage:.2f}x>{policy.max_perp_leverage:.2f}x"
        )
    if pyth_conf_bps > policy.max_pyth_conf_bps:
        violations.append(
            f"pyth_oracle_confidence_too_wide:{pyth_conf_bps}>{policy.max_pyth_conf_bps}"
        )
    if policy.require_trm_screening and trm_risk_score > policy.max_trm_risk_score:
        violations.append(
            f"trm_counterparty_risk_blocked:{trm_risk_score}>{policy.max_trm_risk_score}"
        )

    if destination_wallets is not None:
        abusive, abuse_reason = detect_route_abuse(
            policy.agent_wallet,
            intermediate_hops or (),
            destination_wallets,
        )
        if abusive and abuse_reason:
            violations.append(f"anti_abuse_guard:{abuse_reason}")

    approved = len(violations) == 0
    decision_payload = {
        "mandate_id": policy.mandate_id,
        "policy_digest": policy.policy_digest(),
        "agent_wallet": policy.agent_wallet,
        "protocol": proto,
        "notional_usd": round(notional_usd, 4),
        "approved": approved,
        "status": "READY_FOR_SIGNATURE_OR_DELEGATED_EXEC" if approved else "BLOCKED_BY_GUARDRAIL",
        "violations": violations,
        "remaining_24h_budget_usd": round(
            max(0.0, policy.max_rolling_24h_spend_usd - rolling_24h_spent_usd - (notional_usd if approved else 0.0)),
            4,
        ),
    }
    receipt_hash = hashlib.sha256(
        json.dumps(decision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    decision_payload["verifiable_receipt"] = f"steve:receipt:v1:{receipt_hash[:32]}"
    return decision_payload


def delegate_subagent_vault(
    parent_policy: MandatePolicy,
    *,
    subagent_id: str,
    role: str,
    vault_address: str,
    allocated_budget_usd: float,
    max_single_tx_usd: float,
    allowed_protocols: Sequence[str],
    existing_delegated_usd: float = 0.0,
    auto_revoke_drawdown_bps: int = 300,
    expires_at_unix: int = 1_800_000_000,
) -> SubAgentDelegation:
    """
    Creates a specialist sub-agent vault delegation while strictly enforcing
    monotone privilege containment (a child vault can never exceed parent privileges).
    """
    if allocated_budget_usd <= 0:
        raise MandateViolationError("Sub-agent allocated_budget_usd must be positive.")
    if existing_delegated_usd + allocated_budget_usd > parent_policy.funded_balance_usd:
        raise MandateViolationError(
            f"Total delegated budget (${existing_delegated_usd + allocated_budget_usd:.2f}) "
            f"exceeds parent funded capital (${parent_policy.funded_balance_usd:.2f})."
        )
    if max_single_tx_usd <= 0 or max_single_tx_usd > parent_policy.max_single_tx_usd:
        raise MandateViolationError(
            f"Sub-agent max_single_tx_usd (${max_single_tx_usd:.2f}) cannot exceed parent cap "
            f"(${parent_policy.max_single_tx_usd:.2f})."
        )
    if auto_revoke_drawdown_bps <= 0 or auto_revoke_drawdown_bps > parent_policy.max_portfolio_drawdown_bps:
        raise MandateViolationError(
            "Sub-agent drawdown threshold cannot be looser than parent drawdown circuit breaker."
        )

    parent_allow = {p.lower() for p in parent_policy.allowed_protocols}
    normalized_child_protos = tuple(dict.fromkeys(p.strip().lower() for p in allowed_protocols if p.strip()))
    if not normalized_child_protos:
        raise MandateViolationError("Sub-agent must specify at least one allowed protocol.")

    escalated = [p for p in normalized_child_protos if p not in parent_allow]
    if escalated:
        raise MandateViolationError(
            f"Privilege escalation blocked: protocols {escalated} not permitted by parent mandate."
        )

    if vault_address.strip() == parent_policy.agent_wallet.strip():
        raise MandateViolationError("Sub-agent dedicated vault must be isolated from main agent wallet.")

    return SubAgentDelegation(
        subagent_id=subagent_id,
        role=role,
        parent_mandate_id=parent_policy.mandate_id,
        vault_address=vault_address.strip(),
        allocated_budget_usd=round(allocated_budget_usd, 2),
        max_single_tx_usd=round(max_single_tx_usd, 2),
        allowed_protocols=normalized_child_protos,
        auto_revoke_drawdown_bps=auto_revoke_drawdown_bps,
        expires_at_unix=expires_at_unix,
    )


def compute_barbell_strategy(
    policy: MandatePolicy,
    opportunities: Sequence[MarketOpportunity] | None = None,
    *,
    dry_powder_floor_bps: int = 1500,
    risk_free_rate_bps: int = 450,
) -> dict[str, Any]:
    """
    Computes a Pyth-oracle-filtered, quarter-Kelly risk-adjusted Barbell allocation
    across Kamino yield vaults, Meteora/Raydium LPs, and Adrena/Phoenix perpetual carry.
    Guarantees exact 10,000 bps conservation.
    """
    if not (500 <= dry_powder_floor_bps <= 5000):
        raise ValueError("dry_powder_floor_bps must be between 500 and 5000 bps.")

    market_list = list(opportunities) if opportunities is not None else list(DEFAULT_MARKET_SNAPSHOT)
    parent_allow = {p.lower() for p in policy.allowed_protocols}

    eligible: list[tuple[MarketOpportunity, float]] = []
    rejected: list[dict[str, Any]] = []

    for opp in market_list:
        proto = opp.protocol.lower()
        if proto not in parent_allow:
            rejected.append({"venue": opp.venue, "reason": "protocol_not_allowlisted"})
            continue
        if opp.pyth_conf_bps > policy.max_pyth_conf_bps:
            rejected.append({"venue": opp.venue, "reason": f"pyth_conf_bps_{opp.pyth_conf_bps}_exceeds_limit"})
            continue

        excess_return = (opp.expected_net_apr_bps - risk_free_rate_bps) / 10_000.0
        vol = max(opp.annualized_volatility_bps / 10_000.0, 0.02)
        if excess_return <= 0:
            rejected.append({"venue": opp.venue, "reason": "non_positive_excess_yield"})
            continue

        # Quarter-Kelly score bounded for fat-tailed Solana/commodity regimes
        raw_kelly = excess_return / (vol * vol)
        quarter_kelly_score = min(max(raw_kelly * 0.25, 0.05), 2.50)
        eligible.append((opp, quarter_kelly_score))

    allocatable_bps = 10_000 - dry_powder_floor_bps
    allocations: list[dict[str, Any]] = []

    if not eligible:
        return {
            "mandate_id": policy.mandate_id,
            "capital_usd": round(policy.funded_balance_usd, 2),
            "weighted_expected_apr_bps": risk_free_rate_bps,
            "total_weight_bps": 10_000,
            "allocations": [
                {
                    "venue": "USDC Treasury Vault Reserve",
                    "protocol": "multihopper",
                    "asset_pair": "USDC",
                    "category": "reserve",
                    "weight_bps": 10_000,
                    "allocated_usd": round(policy.funded_balance_usd, 2),
                    "expected_net_apr_bps": risk_free_rate_bps,
                }
            ],
            "rejected_opportunities": rejected,
        }

    total_score = sum(score for _, score in eligible)
    # Cap any single volatile sleeve (spot_lp / perp_*) at 3000 bps for barbell safety
    raw_bps: list[int] = []
    for opp, score in eligible:
        share = round(allocatable_bps * (score / total_score))
        if opp.category != "yield":
            share = min(share, 3000)
        raw_bps.append(share)

    # Route any leftover bps from volatile caps into the lowest-volatility yield anchor or dry powder
    assigned_bps = sum(raw_bps)
    remainder_bps = allocatable_bps - assigned_bps
    yield_indices = [i for i, (opp, _) in enumerate(eligible) if opp.category == "yield"]
    if remainder_bps != 0 and yield_indices:
        raw_bps[yield_indices[0]] += remainder_bps
        remainder_bps = 0

    final_dry_powder_bps = dry_powder_floor_bps + remainder_bps

    weighted_apr_accum = 0.0
    for (opp, _), w_bps in zip(eligible, raw_bps):
        usd_amt = round(policy.funded_balance_usd * (w_bps / 10_000.0), 2)
        weighted_apr_accum += opp.expected_net_apr_bps * (w_bps / 10_000.0)
        allocations.append(
            {
                "venue": opp.venue,
                "protocol": opp.protocol,
                "asset_pair": opp.asset_pair,
                "category": opp.category,
                "weight_bps": w_bps,
                "allocated_usd": usd_amt,
                "expected_net_apr_bps": opp.expected_net_apr_bps,
                "pyth_conf_bps": opp.pyth_conf_bps,
            }
        )

    allocations.append(
        {
            "venue": "MultiHopper Programmable USDC Reserve",
            "protocol": "multihopper",
            "asset_pair": "USDC",
            "category": "reserve",
            "weight_bps": final_dry_powder_bps,
            "allocated_usd": round(policy.funded_balance_usd * (final_dry_powder_bps / 10_000.0), 2),
            "expected_net_apr_bps": 0,
            "pyth_conf_bps": 0,
        }
    )

    total_bps_check = sum(item["weight_bps"] for item in allocations)
    assert total_bps_check == 10_000, f"Barbell conservation invariant broken: {total_bps_check}"

    return {
        "mandate_id": policy.mandate_id,
        "capital_usd": round(policy.funded_balance_usd, 2),
        "weighted_expected_apr_bps": round(weighted_apr_accum),
        "total_weight_bps": total_bps_check,
        "allocations": allocations,
        "rejected_opportunities": rejected,
    }


def compute_multihopper_onchain_fees(
    hop_amount_usd: float,
    *,
    hops: int,
    destination_count: int = 1,
) -> dict[str, Any]:
    """
    Computes the official MultiHopper mainnet 10-tier fee schedule:
      - `0.50%` (`50 bps`) percent fee split 50/50 atomically on-chain (`25 bps` integrator share).
      - Tier 0..9 per-hop lamport fee (`0` up to `2,000,000` lamports/hop above $500).
      - `0.002 SOL` (`2,000,000` lamports) TRM Labs compliance screening fee per screened wallet.
    """
    if hop_amount_usd < 0:
        raise ValueError("hop_amount_usd must be non-negative")
    effective_hops = max(3, min(10, int(hops)))
    dest_cnt = max(1, min(20, int(destination_count)))

    tier_index = 9
    per_hop_lamports = MULTIHOPPER_TOP_TIER_LAMPORTS_PER_HOP
    for idx, (upper_usd, lamports) in enumerate(MULTIHOPPER_FEE_TIERS_USD_LAMPORTS):
        if hop_amount_usd <= upper_usd:
            tier_index = idx
            per_hop_lamports = lamports
            break

    total_flat_fee_lamports = per_hop_lamports * effective_hops
    # Sender + destinations screened on mainnet compliance-enabled deployments
    screened_wallets = 1 + dest_cnt
    screening_fee_lamports = screened_wallets * MULTIHOPPER_TRM_SCREENING_LAMPORTS_PER_WALLET
    dispersion_rent_lamports = (dest_cnt * 1_461_600) if dest_cnt > 1 else 0
    required_sol_upfront_lamports = (
        total_flat_fee_lamports + screening_fee_lamports + dispersion_rent_lamports + 150_000
    )

    percent_fee_usd = round(hop_amount_usd * (MULTIHOPPER_PERCENT_FEE_BPS / 10_000.0), 6)
    integrator_share_usd = round(percent_fee_usd * 0.5, 6)

    return {
        "tierIndex": tier_index,
        "usdValueMicros": round(hop_amount_usd * 1_000_000),
        "percentFeeBps": MULTIHOPPER_PERCENT_FEE_BPS,
        "integratorShareBps": 25,
        "percentFeeUsd": percent_fee_usd,
        "integratorPercentShareUsd": integrator_share_usd,
        "perHopFlatLamports": per_hop_lamports,
        "effectiveProtocolHops": effective_hops,
        "totalFlatFeeLamports": total_flat_fee_lamports,
        "sol": {
            "requiredSolUpFrontLamports": required_sol_upfront_lamports,
            "breakdown": {
                "screeningFeeLamports": screening_fee_lamports,
                "dispersionRentLamports": dispersion_rent_lamports,
                "keeperAndNetworkBufferLamports": 150_000,
            },
        },
        "priceSource": "onchain_pool",
    }


def plan_multihopper_route(
    policy: MandatePolicy,
    *,
    input_token: str,
    input_amount: float,
    output_token: str,
    recipients: Sequence[dict[str, Any]],
    intermediate_venues: Sequence[str] = ("Meteora DLMM", "Orca Whirlpool"),
    trm_max_observed_risk: int = 5,
    rolling_24h_spent_usd: float = 0.0,
) -> dict[str, Any]:
    """
    Plans a non-custodial MultiHopper route for a Steve Capital autonomous agent:
      1. Enforces exact 10,000 bps split conservation across recipients.
      2. Counts routed principal ONCE per route (regardless of intermediate hops),
         matching the MultiHopper x Steve Capital Challenge specification.
      3. Runs Mandate + TRM counterparty risk + Anti-Wash/Circularity checks.
      4. Verifies Solana VersionedTransaction (v0) + ALT packet compression (<= 1232 bytes).
    """
    in_sym = input_token.strip().upper()
    out_sym = output_token.strip().upper()
    if in_sym not in TOKEN_USD_REFERENCE or out_sym not in TOKEN_USD_REFERENCE:
        raise ValueError(f"Unsupported token symbol: {in_sym} -> {out_sym}")
    if input_amount <= 0:
        raise ValueError("input_amount must be > 0")
    if not recipients:
        raise ValueError("At least one recipient split is required.")
    if len(recipients) > 20:
        raise MandateViolationError(
            f"MH_017: MultiHopper multi-destination routes support at most 20 destinations (got {len(recipients)})."
        )

    split_bps_total = sum(int(r.get("share_bps", 0)) for r in recipients)
    if split_bps_total != 10_000:
        raise ValueError(f"Recipient shares must sum to 10000 bps (got {split_bps_total}).")

    dest_wallets = [str(r.get("wallet", "")).strip() for r in recipients]
    principal_usd = round(input_amount * TOKEN_USD_REFERENCE[in_sym], 4)

    # Estimate price impact improvement from split routing across venues
    hop_count = max(1, len(intermediate_venues))
    estimated_slippage_bps = max(8, round(22 / math.sqrt(hop_count)))

    guardrail = evaluate_mandate_action(
        policy,
        protocol="multihopper",
        notional_usd=principal_usd,
        rolling_24h_spent_usd=rolling_24h_spent_usd,
        estimated_slippage_bps=estimated_slippage_bps,
        trm_risk_score=trm_max_observed_risk,
        destination_wallets=dest_wallets,
        intermediate_hops=intermediate_venues,
    )
    if not guardrail["approved"]:
        raise MandateViolationError(
            "MultiHopper route blocked by Steve Capital Mandate: " + ", ".join(guardrail["violations"])
        )

    net_factor = 1.0 - (estimated_slippage_bps / 10_000.0)
    total_output_units = (principal_usd * net_factor) / TOKEN_USD_REFERENCE[out_sym]

    disbursements: list[dict[str, Any]] = []
    for r in recipients:
        share_bps = int(r["share_bps"])
        amt_out = round(total_output_units * (share_bps / 10_000.0), 6)
        disbursements.append(
            {
                "wallet": str(r["wallet"]).strip(),
                "label": str(r.get("label", "recipient")),
                "share_bps": share_bps,
                "amount_out": amt_out,
                "token": out_sym,
            }
        )

    # Solana v0 + ALT byte budget model:
    # Header + signature(64B) + blockhash(32B) + ALT header(34B) + 1B account indexes + compact ix data
    indexed_accounts = 6 + (hop_count * 5) + (len(recipients) * 2)
    legacy_bytes = 130 + (indexed_accounts * 32) + (hop_count * 44) + (len(recipients) * 28)
    v0_alt_bytes = 164 + indexed_accounts + (hop_count * 36) + (len(recipients) * 21)
    if v0_alt_bytes > SOLANA_MAX_PACKET_BYTES:
        raise MandateViolationError(
            f"v0+ALT transaction ({v0_alt_bytes}B) exceeds Solana {SOLANA_MAX_PACKET_BYTES}B packet limit."
        )

    route_digest = hashlib.sha256(
        json.dumps(
            {
                "agent_wallet": policy.agent_wallet,
                "in": f"{input_amount}:{in_sym}",
                "out": out_sym,
                "venues": list(intermediate_venues),
                "disbursements": disbursements,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "status": "PREPARED_AWAITING_AGENT_SIGNATURE",
        "agent_wallet": policy.agent_wallet,
        "input": {"token": in_sym, "amount": input_amount},
        "output": {"token": out_sym, "estimated_total_amount": round(total_output_units, 6)},
        "intermediate_hops": list(intermediate_venues),
        "hop_count": hop_count,
        "verified_routed_principal_usd": round(principal_usd, 2),
        "principal_counted_once": True,
        "trm_screening": {
            "passed": True,
            "max_observed_risk_score": trm_max_observed_risk,
            "policy_ceiling": policy.max_trm_risk_score,
        },
        "anti_wash_verification": {
            "self_transfer": False,
            "circular_hops": False,
            "duplicate_recipients": False,
        },
        "solana_v0_packet": {
            "version": "v0",
            "alt_enabled": True,
            "indexed_accounts": indexed_accounts,
            "legacy_uncompressed_bytes": legacy_bytes,
            "v0_compressed_bytes": v0_alt_bytes,
            "max_packet_limit_bytes": SOLANA_MAX_PACKET_BYTES,
            "fits_single_atomic_tx": v0_alt_bytes <= SOLANA_MAX_PACKET_BYTES,
        },
        "disbursements": disbursements,
        "multihopper_broadcast_plan": {
            "expectedSigner": policy.agent_wallet,
            "maxHopGroups": 25,
            "totalGroups": 1 + hop_count,
            "withinGroupCeiling": (1 + hop_count) <= 25,
            "relayEndpoint": "/api/multihopper/broadcast",
            "groups": [
                {
                    "groupIndex": 0,
                    "kind": "orchestratorInit",
                    "txFormat": "legacy",
                    "signingMode": "partialSign",
                },
                *[
                    {
                        "groupIndex": idx + 1,
                        "kind": "hopExecution",
                        "venue": venue,
                        "txFormat": "v0",
                        "signingMode": "sign",
                    }
                    for idx, venue in enumerate(intermediate_venues)
                ],
            ],
        },
        "mandate_receipt": guardrail["verifiable_receipt"],
        "multihopper_route_id": f"mh:route:v1:{route_digest[:28]}",
        "multihopper_programs": {
            "core": MULTIHOPPER_CORE_PROGRAM_ID,
            "orchestrator": MULTIHOPPER_ORCHESTRATOR_PROGRAM_ID,
            "transferHookGuardToken2022": MULTIHOPPER_TRANSFER_HOOK_PROGRAM_ID,
        },
        "multihopper_onchain_fees": compute_multihopper_onchain_fees(
            principal_usd * net_factor,
            hops=max(3, hop_count),
            destination_count=len(recipients),
        ),
        "multihopper_v1_agentic_flow": {
            "mcpEndpoint": "https://multihopper.com/api/mcp",
            "restBase": "https://multihopper.com/api/v1",
            "idempotencyKey": f"idem-{route_digest[:24]}",
            "externalId": f"steve-{policy.mandate_id}-{route_digest[:12]}",
            "twoPhaseConfirmBroadcast": True,
            "strictBroadcastOrder": [
                {
                    "step": 1,
                    "group": "keeperFundingTx",
                    "txFormat": "v0",
                    "signingRule": "slot_preserve_ephemeral_sigs",
                    "postConfirmAction": "POST /api/v1/transfers/{id}/confirm-broadcast (keeperFundingSignature ONLY — prevents double-funding, MH_039 guard)",
                },
                {
                    "step": 2,
                    "group": "routeInitTxs",
                    "txFormat": "v0",
                    "signingRule": "slot_preserve_ephemeral_sigs",
                    "postConfirmDelaySec": 3,
                },
                {
                    "step": 3,
                    "group": "orchestratorInitTx",
                    "txFormat": "legacy",
                    "signingRule": "partialSign",
                    "postConfirmDelaySec": 3,
                },
                {
                    "step": 4,
                    "group": "sessionInitTxs",
                    "txFormat": "v0",
                    "signingRule": "slot_preserve_ephemeral_sigs",
                },
                *(
                    [
                        {
                            "step": 5,
                            "group": "dispersionInitTxs",
                            "txFormat": "v0",
                            "signingRule": "sourceOwner_sign",
                            "exitBindingGuard": "MH_041_all_destinations_bound_before_activation",
                        }
                    ]
                    if len(recipients) > 1
                    else []
                ),
            ],
        },
    }
