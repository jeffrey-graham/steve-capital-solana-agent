"""
Partner Side-Track & Ecosystem Privacy Integrations
===================================================
Implements:
  1. Ace Data Cloud x Steve Capital Side-Track:
     - Macro/market intelligence regime synthesizer (`synthesize_acedata_macro_brief`)
       converting structured Ace MCP search/research signals + Pyth confidence spreads
       into risk-adjusted Steve Capital mandate overrides and narrated audio/video scripts.
     - Strict 5-paid-request side-track ledger verifier (`verify_acedata_side_track_ledger`)
       enforcing purchased-credit provenance (excluding free-trial/promotional credits and
       repetitive/duplicate query spam).
  2. MagicBlock Ephemeral Rollup Private Settlement (`plan_magicblock_private_settlement`):
     - Plans privacy-preserving SPL token transfers/swaps inside scoped Ephemeral Rollup
       sessions while enforcing pre-shielding TRM counterparty screening, anti-self-transfer
       rules, bounded session-key TTLs, and Steve Capital spending limits.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from typing import Any

from src.capital_engine import (
    TOKEN_USD_REFERENCE,
    MandatePolicy,
    MandateViolationError,
    evaluate_mandate_action,
)

ACE_MCP_DEFAULT_URL = "https://api.acedata.cloud/mcp"
ACE_MIN_QUALIFYING_PAID_REQUESTS = 5
ACE_SUPPORTED_TOOLS = frozenset(
    {
        "ace_google_search",
        "ace_deep_research",
        "ace_tts_narrate",
        "ace_image_render",
        "ace_video_brief",
    }
)


@dataclasses.dataclass(frozen=True)
class AceServiceCallRecord:
    request_id: str
    tool_name: str
    status: str  # "succeeded" | "failed"
    credit_source: str  # "purchased" | "free_trial" | "promotional"
    credits_spent: float
    query_fingerprint: str
    timestamp_unix: int


def verify_acedata_side_track_ledger(
    agent_wallet: str,
    records: Sequence[dict[str, Any] | AceServiceCallRecord],
    *,
    min_paid_requests: int = ACE_MIN_QUALIFYING_PAID_REQUESTS,
) -> dict[str, Any]:
    """
    Audits Ace Data Cloud MCP usage records against the official challenge rules:
      - Requires >= 5 successful requests funded by *purchased* Ace credits.
      - Excludes requests funded by free trial or promotional credits.
      - Excludes failed requests, duplicate request IDs, and repetitive artificial
        queries (duplicate `query_fingerprint`).
    """
    wallet_norm = agent_wallet.strip()
    if not wallet_norm:
        raise ValueError("agent_wallet cannot be empty")

    qualifying: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_request_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    total_purchased_credits = 0.0

    for raw in records:
        rec = (
            dataclasses.asdict(raw)
            if isinstance(raw, AceServiceCallRecord)
            else dict(raw)
        )
        req_id = str(rec.get("request_id", "")).strip()
        tool = str(rec.get("tool_name", "")).strip()
        status = str(rec.get("status", "")).strip().lower()
        source = str(rec.get("credit_source", "")).strip().lower()
        spent = float(rec.get("credits_spent", 0.0))
        fp = str(rec.get("query_fingerprint", "")).strip()

        if not req_id:
            excluded.append({"request_id": "", "reason": "missing_request_id"})
            continue
        if req_id in seen_request_ids:
            excluded.append({"request_id": req_id, "reason": "duplicate_request_id"})
            continue
        seen_request_ids.add(req_id)

        if tool not in ACE_SUPPORTED_TOOLS:
            excluded.append({"request_id": req_id, "reason": f"unsupported_ace_tool:{tool}"})
            continue
        if status != "succeeded":
            excluded.append({"request_id": req_id, "reason": f"non_succeeded_status:{status}"})
            continue
        if source != "purchased":
            excluded.append(
                {
                    "request_id": req_id,
                    "reason": f"non_purchased_credits_excluded:{source}",
                }
            )
            continue
        if spent <= 0.0:
            excluded.append({"request_id": req_id, "reason": "zero_or_negative_credits_spent"})
            continue
        if not fp or fp in seen_fingerprints:
            excluded.append(
                {
                    "request_id": req_id,
                    "reason": "repetitive_or_duplicate_query_fingerprint",
                }
            )
            continue

        seen_fingerprints.add(fp)
        total_purchased_credits += spent
        qualifying.append(
            {
                "request_id": req_id,
                "tool_name": tool,
                "credits_spent": round(spent, 4),
                "query_fingerprint": fp,
            }
        )

    eligible = len(qualifying) >= min_paid_requests
    summary = {
        "agent_wallet": wallet_norm,
        "ace_mcp_endpoint": ACE_MCP_DEFAULT_URL,
        "qualifying_paid_requests": len(qualifying),
        "minimum_required_paid_requests": min_paid_requests,
        "side_track_eligible": eligible,
        "remaining_paid_requests_needed": max(0, min_paid_requests - len(qualifying)),
        "total_purchased_credits_spent": round(total_purchased_credits, 4),
        "verified_requests": qualifying,
        "excluded_requests": excluded,
    }
    digest = hashlib.sha256(
        json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    summary["ace_verification_receipt"] = f"ace:eligibility:v1:{digest[:28]}"
    return summary


DEFAULT_ACE_SIGNALS: list[dict[str, Any]] = [
    {
        "topic": "Solana DEX Liquidity & Kamino Utilization",
        "sentiment_bps": 2400,
        "inflation_shock": False,
        "volatility_alert": False,
        "source": "ace_google_search",
    },
    {
        "topic": "Macro Gold (XAU) & WTI Crude Supply Hedging",
        "sentiment_bps": 1800,
        "inflation_shock": True,
        "volatility_alert": False,
        "source": "ace_deep_research",
    },
]


def synthesize_acedata_macro_brief(
    policy: MandatePolicy,
    *,
    signals: Sequence[dict[str, Any]] | None = None,
    pyth_sol_conf_bps: int = 9,
    pyth_xau_conf_bps: int = 12,
    paid_ledger: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Synthesizes Ace Data Cloud research/search intelligence and Pyth oracle
    confidence intervals into a deterministic Steve Capital portfolio regime,
    mandate parameter recommendations, and a narrated executive briefing script.
    """
    items = list(signals) if signals is not None else list(DEFAULT_ACE_SIGNALS)
    if not items:
        raise ValueError("At least one intelligence signal is required.")

    avg_sentiment_bps = round(sum(int(s.get("sentiment_bps", 0)) for s in items) / len(items))
    any_vol_alert = any(bool(s.get("volatility_alert", False)) for s in items)
    any_inflation = any(bool(s.get("inflation_shock", False)) for s in items)
    wide_oracle = (
        pyth_sol_conf_bps > policy.max_pyth_conf_bps
        or pyth_xau_conf_bps > policy.max_pyth_conf_bps
    )

    if any_vol_alert or wide_oracle or avg_sentiment_bps <= -1500:
        regime = "DEFENSIVE_DELEVERAGE"
        rec_dry_powder_bps = min(5000, 3500)
        rec_max_leverage = 1.0
        adrena_xau_tilt_bps = 1000
    elif any_inflation:
        regime = "COMMODITY_INFLATION_HEDGE"
        rec_dry_powder_bps = 2000
        rec_max_leverage = min(policy.max_perp_leverage, 2.0)
        adrena_xau_tilt_bps = 2500
    else:
        regime = "RISK_ON_BARBELL_CARRY"
        rec_dry_powder_bps = 1500
        rec_max_leverage = policy.max_perp_leverage
        adrena_xau_tilt_bps = 1500

    narration_script = (
        f"StevePulse Executive Brief for mandate {policy.mandate_id}: "
        f"Active regime is {regime.replace('_', ' ')} with composite sentiment {avg_sentiment_bps} bps "
        f"and Pyth confidence spreads of {pyth_sol_conf_bps} bps on SOL and {pyth_xau_conf_bps} bps on Gold. "
        f"Recommended reserve floor is {rec_dry_powder_bps / 100:.1f}% USDC, maximum perp leverage "
        f"{rec_max_leverage:.2f}x, and Adrena XAU-PERP basis weight {adrena_xau_tilt_bps / 100:.1f}%."
    )

    ledger_audit = (
        verify_acedata_side_track_ledger(policy.agent_wallet, paid_ledger)
        if paid_ledger is not None
        else None
    )

    brief = {
        "mandate_id": policy.mandate_id,
        "agent_wallet": policy.agent_wallet,
        "regime": regime,
        "signal_count": len(items),
        "composite_sentiment_bps": avg_sentiment_bps,
        "oracle_telemetry": {
            "sol_usd_conf_bps": pyth_sol_conf_bps,
            "xau_usd_conf_bps": pyth_xau_conf_bps,
            "within_policy_ceiling": not wide_oracle,
        },
        "recommended_mandate_overrides": {
            "dry_powder_floor_bps": rec_dry_powder_bps,
            "max_perp_leverage": rec_max_leverage,
            "adrena_xau_hedge_tilt_bps": adrena_xau_tilt_bps,
        },
        "ace_tts_narration_script": narration_script,
        "ace_side_track_verification": ledger_audit,
    }
    digest = hashlib.sha256(
        json.dumps(brief, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    brief["brief_receipt"] = f"ace:brief:v1:{digest[:28]}"
    return brief


def plan_magicblock_private_settlement(
    policy: MandatePolicy,
    *,
    token: str,
    amount: float,
    recipient_wallet: str,
    session_ttl_seconds: int = 900,
    commit_interval_ms: int = 5000,
    trm_risk_score: int = 3,
    rolling_24h_spent_usd: float = 0.0,
) -> dict[str, Any]:
    """
    Plans a confidential SPL transfer/settlement via MagicBlock Ephemeral Rollups
    while enforcing pre-shielding TRM screening, anti-self-transfer invariants,
    least-privilege session key TTLs (`60s..3600s`), and parent mandate caps.
    """
    sym = token.strip().upper()
    if sym not in TOKEN_USD_REFERENCE:
        raise ValueError(f"Unsupported token for MagicBlock settlement: {sym}")
    if amount <= 0:
        raise ValueError("Settlement amount must be > 0")
    if not (60 <= session_ttl_seconds <= 3600):
        raise MandateViolationError(
            f"MagicBlock session_ttl_seconds ({session_ttl_seconds}s) must be within [60, 3600] for least-privilege safety."
        )
    if not (500 <= commit_interval_ms <= 30_000):
        raise ValueError("commit_interval_ms must be between 500ms and 30000ms")

    recip = recipient_wallet.strip()
    notional_usd = round(amount * TOKEN_USD_REFERENCE[sym], 4)

    guardrail = evaluate_mandate_action(
        policy,
        protocol="magicblock",
        notional_usd=notional_usd,
        rolling_24h_spent_usd=rolling_24h_spent_usd,
        estimated_slippage_bps=5,
        trm_risk_score=trm_risk_score,
        destination_wallets=[recip],
    )
    if not guardrail["approved"]:
        raise MandateViolationError(
            "MagicBlock private settlement blocked by Steve Capital Mandate: "
            + ", ".join(guardrail["violations"])
        )

    plan = {
        "status": "PREPARED_EPHEMERAL_ROLLUP_DELEGATION",
        "protocol": "magicblock",
        "agent_wallet": policy.agent_wallet,
        "recipient_wallet": recip,
        "asset": {"token": sym, "amount": amount, "notional_usd": round(notional_usd, 2)},
        "ephemeral_rollup_session": {
            "session_ttl_seconds": session_ttl_seconds,
            "state_root_commit_interval_ms": commit_interval_ms,
            "scoped_program": "SPL-Token-Confidential-ER",
            "auto_undelegate_on_expiry": True,
        },
        "pre_shield_compliance": {
            "trm_screened_before_shielding": True,
            "trm_risk_score": trm_risk_score,
            "self_transfer_blocked": True,
        },
        "mandate_receipt": guardrail["verifiable_receipt"],
    }
    digest = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    plan["magicblock_session_id"] = f"mb:er-session:v1:{digest[:28]}"
    return plan
