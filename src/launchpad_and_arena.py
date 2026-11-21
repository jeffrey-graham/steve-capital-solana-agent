"""
Steve Launchpad Anti-Rug Guard, Verified Arena XP Ledger & x402 Payment Verifier
================================================================================
Completes the full Steve Capital Agent Challenge ecosystem scope:
  1. `audit_steve_launchpad_manifest`:
     Audits token launch manifests on Steve Launchpad (mint/freeze authority
     revocation, initial USDC liquidity bounds, insider supply ceiling, Token-2022
     transfer-fee ceiling, and HTTPS/IPFS Metaplex metadata verification).
  2. `score_verified_arena_xp_ledger`:
     Computes Sybil-resistant Steve Arena XP across official challenge categories
     while excluding underfunded (`< $20 USD`) wallets, self-transfers, circular
     routes, duplicate transaction signatures, and repetitive spam bursts.
  3. `build_x402_payment_challenge` & `verify_x402_agent_payment_envelope`:
     Implements HTTP 402 (`x402` v1 Solana SPL USDC) challenge generation and
     agent-to-agent micro-USDC payment envelope verification inside Agent Space.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from src.capital_engine import (
    STEVE_MIN_ARENA_FUNDING_USD,
    MandatePolicy,
)
from src.solana_telemetry import (
    SOLANA_USDC_MINT,
    is_valid_solana_pubkey,
)

LAUNCHPAD_MIN_INITIAL_LIQUIDITY_USD = 50.0
LAUNCHPAD_MAX_INSIDER_ALLOCATION_BPS = 2000  # <= 20.00%
LAUNCHPAD_MIN_GRADUATION_MC_USD = 25_000.0
LAUNCHPAD_MAX_TOKEN2022_FEE_BPS = 250  # <= 2.50%

ARENA_XP_WEIGHTS: dict[str, int] = {
    "strategy_publish": 120,
    "multihopper_mainnet_route": 180,
    "subagent_delegation": 140,
    "acedata_paid_brief": 150,
    "magicblock_private_settlement": 160,
    "launchpad_verified_deploy": 175,
}
ARENA_MAX_CREDITED_PER_CATEGORY = 8

DEFAULT_X402_RESOURCE_URI = (
    "https://jeffrey-graham.github.io/steve-capital-solana-agent/.well-known/x402.json"
)


def _is_public_metadata_uri(uri: str) -> bool:
    cleaned = (uri or "").strip()
    if not cleaned.startswith(("https://", "ipfs://", "ar://")):
        return False
    lowered = cleaned.lower()
    for bad in ("localhost", "127.0.0.1", "file://", "/home/", "c:\\"):
        if bad in lowered:
            return False
    return True


def audit_steve_launchpad_manifest(
    policy: MandatePolicy,
    *,
    token_name: str,
    token_symbol: str,
    metadata_uri: str,
    initial_liquidity_usdc: float,
    total_supply: int = 1_000_000_000,
    creator_allocation_bps: int = 1000,
    mint_authority_revoked: bool = True,
    freeze_authority_revoked: bool = True,
    token2022_transfer_fee_bps: int = 0,
    graduation_market_cap_usd: float = 69_000.0,
) -> dict[str, Any]:
    """
    Audits a proposed Steve Launchpad token launch against anti-rug invariants AND
    the parent Steve Capital `MandatePolicy` spending/funding guardrails.
    """
    violations: list[str] = []
    clean_name = (token_name or "").strip()
    clean_symbol = (token_symbol or "").strip().upper()

    if policy.funded_balance_usd < STEVE_MIN_ARENA_FUNDING_USD:
        violations.append(
            f"arena_funding_below_20_usd:{policy.funded_balance_usd:.2f}<{STEVE_MIN_ARENA_FUNDING_USD:.2f}"
        )
    if not (2 <= len(clean_name) <= 32):
        violations.append("invalid_token_name_length_2_to_32")
    if not (2 <= len(clean_symbol) <= 10 and clean_symbol.isalnum()):
        violations.append("invalid_token_symbol_alnum_2_to_10")
    if not _is_public_metadata_uri(metadata_uri):
        violations.append("metadata_uri_must_be_public_https_ipfs_or_arweave")
    if total_supply <= 0:
        violations.append("total_supply_must_be_positive")
    if initial_liquidity_usdc < LAUNCHPAD_MIN_INITIAL_LIQUIDITY_USD:
        violations.append(
            f"initial_liquidity_below_floor:{initial_liquidity_usdc:.2f}<{LAUNCHPAD_MIN_INITIAL_LIQUIDITY_USD:.2f}"
        )
    if initial_liquidity_usdc > policy.max_single_tx_usd:
        violations.append(
            f"initial_liquidity_exceeds_mandate_single_tx:{initial_liquidity_usdc:.2f}>{policy.max_single_tx_usd:.2f}"
        )
    if not mint_authority_revoked:
        violations.append("anti_rug_guard:mint_authority_must_be_revoked")
    if not freeze_authority_revoked:
        violations.append("anti_rug_guard:freeze_authority_must_be_revoked")
    if not (0 <= creator_allocation_bps <= LAUNCHPAD_MAX_INSIDER_ALLOCATION_BPS):
        violations.append(
            f"insider_allocation_exceeds_2000_bps:{creator_allocation_bps}>{LAUNCHPAD_MAX_INSIDER_ALLOCATION_BPS}"
        )
    if not (0 <= token2022_transfer_fee_bps <= LAUNCHPAD_MAX_TOKEN2022_FEE_BPS):
        violations.append(
            f"token2022_transfer_fee_exceeds_250_bps:{token2022_transfer_fee_bps}>{LAUNCHPAD_MAX_TOKEN2022_FEE_BPS}"
        )
    if graduation_market_cap_usd < LAUNCHPAD_MIN_GRADUATION_MC_USD:
        violations.append(
            f"graduation_mc_below_25k_usd:{graduation_market_cap_usd:.2f}<{LAUNCHPAD_MIN_GRADUATION_MC_USD:.2f}"
        )

    approved = len(violations) == 0
    curve_supply_bps = 10_000 - max(0, min(10_000, creator_allocation_bps))
    digest_payload = json.dumps(
        {
            "mandate": policy.mandate_id,
            "symbol": clean_symbol,
            "uri": metadata_uri,
            "liq": round(initial_liquidity_usdc, 2),
            "creator_bps": creator_allocation_bps,
        },
        sort_keys=True,
    ).encode("utf-8")
    receipt_hash = hashlib.sha256(digest_payload).hexdigest()[:16]

    return {
        "approved": approved,
        "status": "ELIGIBLE_FOR_STEVE_LAUNCHPAD" if approved else "BLOCKED_BY_LAUNCHPAD_GUARDRAIL",
        "token_spec": {
            "name": clean_name,
            "symbol": clean_symbol,
            "metadata_uri": metadata_uri,
            "total_supply": total_supply,
            "creator_allocation_bps": creator_allocation_bps,
            "bonding_curve_public_bps": curve_supply_bps,
            "initial_liquidity_usdc": round(initial_liquidity_usdc, 2),
            "graduation_market_cap_usd": round(graduation_market_cap_usd, 2),
            "token2022_transfer_fee_bps": token2022_transfer_fee_bps,
        },
        "security_invariants": {
            "mint_authority_revoked": bool(mint_authority_revoked),
            "freeze_authority_revoked": bool(freeze_authority_revoked),
            "supply_bps_conserved": (creator_allocation_bps + curve_supply_bps) == 10_000,
            "within_single_tx_mandate": initial_liquidity_usdc <= policy.max_single_tx_usd,
        },
        "violations": violations,
        "launchpad_audit_receipt": f"steve:launchpad:v1:{receipt_hash}",
    }


def score_verified_arena_xp_ledger(
    policy: MandatePolicy,
    activities: Sequence[dict[str, Any]],
    *,
    require_finalized_onchain: bool = True,
) -> dict[str, Any]:
    """
    Evaluates a sequence of Steve Capital agent activities and computes verified
    Arena XP while filtering out ineligible, duplicate, circular, self-transfer,
    or spam-burst events per official challenge rules.
    """
    arena_funded = policy.funded_balance_usd >= STEVE_MIN_ARENA_FUNDING_USD
    seen_refs: set[str] = set()
    category_counts: dict[str, int] = {}
    credited: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total_xp = 0
    verified_routed_usd = 0.0

    for idx, ev in enumerate(activities):
        ref = str(ev.get("tx_signature") or ev.get("activity_id") or f"idx-{idx}").strip()
        category = str(ev.get("category") or "").strip()
        finalized = bool(ev.get("finalized_onchain", False))
        is_self = bool(ev.get("self_transfer", False)) or (
            ev.get("origin_wallet")
            and ev.get("destination_wallet")
            and ev.get("origin_wallet") == ev.get("destination_wallet")
        )
        is_circular = bool(ev.get("circular_route", False))

        if not arena_funded:
            excluded.append({"ref": ref, "reason": "agent_wallet_below_20_usd_arena_floor"})
            continue
        if category not in ARENA_XP_WEIGHTS:
            excluded.append({"ref": ref, "reason": f"unsupported_activity_category:{category}"})
            continue
        if ref in seen_refs:
            excluded.append({"ref": ref, "reason": "duplicate_signature_or_activity_id"})
            continue
        seen_refs.add(ref)

        if is_self:
            excluded.append({"ref": ref, "reason": "prohibited_self_transfer"})
            continue
        if is_circular:
            excluded.append({"ref": ref, "reason": "prohibited_circular_volume"})
            continue
        if require_finalized_onchain and not finalized:
            excluded.append({"ref": ref, "reason": "unfinalized_or_simulated_activity"})
            continue

        prev_count = category_counts.get(category, 0)
        if prev_count >= ARENA_MAX_CREDITED_PER_CATEGORY:
            excluded.append({"ref": ref, "reason": f"category_anti_spam_cap_reached:{category}"})
            continue

        base_xp = ARENA_XP_WEIGHTS[category]
        # Gentle diminishing-returns decay (100%, 90%, 80%, ..., floor 50%) against repetitive grinding
        decay_factor = max(0.50, 1.0 - 0.10 * prev_count)
        awarded_xp = round(base_xp * decay_factor)
        category_counts[category] = prev_count + 1
        total_xp += awarded_xp

        principal_usd = float(ev.get("principal_usd", 0.0) or 0.0)
        if category == "multihopper_mainnet_route" and principal_usd > 0:
            # MultiHopper rule: origin principal counted strictly once per route regardless of hops
            verified_routed_usd += principal_usd

        credited.append(
            {
                "ref": ref,
                "category": category,
                "awarded_xp": awarded_xp,
                "principal_counted_once_usd": round(principal_usd, 2)
                if category == "multihopper_mainnet_route"
                else 0.0,
            }
        )

    diversity_bonus_xp = 100 if len(category_counts) >= 4 and arena_funded else 0
    final_xp = total_xp + diversity_bonus_xp

    return {
        "arena_eligible": arena_funded and len(credited) > 0,
        "agent_wallet": policy.agent_wallet,
        "funded_balance_usd": round(policy.funded_balance_usd, 2),
        "total_verified_arena_xp": final_xp,
        "ecosystem_diversity_bonus_xp": diversity_bonus_xp,
        "distinct_categories_active": len(category_counts),
        "verified_multihopper_principal_usd": round(verified_routed_usd, 2),
        "credited_count": len(credited),
        "excluded_count": len(excluded),
        "credited_activities": credited,
        "excluded_activities": excluded,
    }


def build_x402_payment_challenge(
    policy: MandatePolicy,
    *,
    service_id: str = "stevepulse:macro-regime-feed",
    price_micro_usdc: int = 1000,
    nonce: str = "x402-nonce-stevepulse-001",
    expires_at_unix: int = 1_800_000_000,
    resource_uri: str = DEFAULT_X402_RESOURCE_URI,
) -> dict[str, Any]:
    """Builds a standards-aligned Solana SPL USDC HTTP 402 (`x402` v1) payment challenge."""
    if price_micro_usdc <= 0:
        raise ValueError("price_micro_usdc must be > 0")
    return {
        "http_status": 402,
        "x402Version": 1,
        "scheme": "exact",
        "network": "solana-mainnet",
        "resource": resource_uri,
        "serviceId": service_id,
        "payTo": policy.agent_wallet,
        "assetMint": SOLANA_USDC_MINT,
        "maxAmountRequired": str(price_micro_usdc),
        "nonce": nonce,
        "expiresAtUnix": expires_at_unix,
    }


def verify_x402_agent_payment_envelope(
    policy: MandatePolicy,
    challenge: dict[str, Any],
    payment_envelope: dict[str, Any],
    *,
    current_unix: int = 1_795_300_000,
    consumed_nonces: Sequence[str] = (),
    max_trm_risk_score: int = 25,
) -> dict[str, Any]:
    """
    Verifies an incoming agent-to-agent `x402` micro-USDC payment envelope before
    releasing gated strategy/macro intelligence inside Steve Capital Agent Space.
    """
    violations: list[str] = []
    payer = str(payment_envelope.get("payerWallet") or "").strip()
    pay_to = str(payment_envelope.get("payTo") or "").strip()
    mint = str(payment_envelope.get("assetMint") or "").strip()
    nonce = str(payment_envelope.get("nonce") or "").strip()
    tx_sig = str(payment_envelope.get("txSignature") or "").strip()
    trm_score = int(payment_envelope.get("trmRiskScore", 0))

    try:
        paid_micro = int(payment_envelope.get("amountMicroUsdc", 0))
    except (TypeError, ValueError):
        paid_micro = 0
    required_micro = int(challenge.get("maxAmountRequired", 0))
    expires_at = int(challenge.get("expiresAtUnix", 0))

    if not is_valid_solana_pubkey(payer):
        violations.append("invalid_payer_solana_pubkey")
    if payer == policy.agent_wallet:
        violations.append("anti_wash_guard:self_payment_prohibited")
    if pay_to != str(challenge.get("payTo")):
        violations.append("recipient_mismatch_against_challenge")
    if mint != SOLANA_USDC_MINT:
        violations.append(f"unsupported_spl_mint:{mint}")
    if paid_micro < required_micro:
        violations.append(f"underpaid_x402_amount:{paid_micro}<{required_micro}")
    if not nonce or nonce != str(challenge.get("nonce")):
        violations.append("challenge_nonce_mismatch")
    if nonce in set(consumed_nonces):
        violations.append("replay_detected:nonce_already_consumed")
    if current_unix > expires_at:
        violations.append(f"challenge_expired:{current_unix}>{expires_at}")
    if trm_score > max_trm_risk_score:
        violations.append(f"trm_counterparty_risk_exceeded:{trm_score}>{max_trm_risk_score}")
    if len(tx_sig) < 32:
        violations.append("missing_or_malformed_solana_tx_signature")

    verified = len(violations) == 0
    return {
        "verified": verified,
        "http_status_unlocked": 200 if verified else 402,
        "serviceId": challenge.get("serviceId"),
        "payerWallet": payer,
        "payTo": pay_to,
        "settledMicroUsdc": paid_micro if verified else 0,
        "settledUsdc": round(paid_micro / 1_000_000, 6) if verified else 0.0,
        "nonce": nonce,
        "violations": violations,
    }
