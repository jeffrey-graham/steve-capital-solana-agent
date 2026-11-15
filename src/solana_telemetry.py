"""
Solana Mainnet-Beta Wallet Readiness & Pyth Hermes v2 Oracle Telemetry
======================================================================
Zero-dependency JSON-RPC and Pyth Hermes v2 client utilities for verifying
Steve Capital Arena wallet funding (`>= $20 USD` in USDC/SOL) and live oracle
confidence spreads (`conf_bps`) prior to autonomous execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any

SOLANA_MAINNET_RPC_URL = "https://api.mainnet-beta.solana.com"
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PYTH_HERMES_LATEST_URL = "https://hermes.pyth.network/v2/updates/price/latest"
COINBASE_SOL_SPOT_URL = "https://api.coinbase.com/v2/prices/SOL-USD/spot"

PYTH_PRICE_FEED_IDS: dict[str, str] = {
    "SOL/USD": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "USDC/USD": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "XAU/USD": "765d2ba906dbc32ca17cc11f5310a89e9ee1f6420508c63861f2f8ba4ee34bb2",
}

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {ch: idx for idx, ch in enumerate(_BASE58_ALPHABET)}


def decode_base58_pubkey(address: str) -> bytes:
    """Decodes a Solana Base58 public key and enforces an exact 32-byte length."""
    cleaned = address.strip()
    if not (32 <= len(cleaned) <= 44):
        raise ValueError(f"Invalid Solana public key length: {len(cleaned)}")

    num = 0
    for ch in cleaned:
        if ch not in _BASE58_INDEX:
            raise ValueError(f"Invalid Base58 character '{ch}' in Solana public key")
        num = num * 58 + _BASE58_INDEX[ch]

    leading_zeros = 0
    for ch in cleaned:
        if ch == "1":
            leading_zeros += 1
        else:
            break

    raw = b"" if num == 0 else num.to_bytes((num.bit_length() + 7) // 8, "big")
    decoded = (b"\x00" * leading_zeros) + raw
    if len(decoded) != 32:
        raise ValueError(f"Decoded Solana public key must be 32 bytes (got {len(decoded)})")
    return decoded


def is_valid_solana_pubkey(address: str) -> bool:
    try:
        decode_base58_pubkey(address)
        return True
    except ValueError:
        return False


def _default_http_get(url: str) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "StevePulse-SAP-Agent/1.2"}
    hermes_key = os.environ.get("PYTH_HERMES_API_KEY", "").strip()
    if hermes_key and "pyth.network" in url:
        headers["Authorization"] = f"Bearer {hermes_key}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_rpc_post(rpc_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "StevePulse-SAP-Agent/1.2",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_pyth_hermes_quotes(
    symbols: Sequence[str] = ("SOL/USD", "XAU/USD"),
    *,
    max_staleness_sec: int = 300,
    now_unix: int | None = None,
    http_get: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Fetches parsed latest price feeds from Pyth Hermes v2 and computes scaled USD
    prices and basis-point confidence intervals (`conf_bps`).
    """
    if not symbols:
        raise ValueError("At least one Pyth symbol is required.")

    id_to_symbol: dict[str, str] = {}
    query_parts = ["parsed=true"]
    for sym in symbols:
        norm_sym = sym.strip().upper()
        if norm_sym not in PYTH_PRICE_FEED_IDS:
            raise ValueError(f"Unsupported Pyth symbol: {norm_sym}")
        feed_id = PYTH_PRICE_FEED_IDS[norm_sym]
        id_to_symbol[feed_id] = norm_sym
        query_parts.append(f"ids%5B%5D=0x{feed_id}")

    getter = http_get or _default_http_get
    url = f"{PYTH_HERMES_LATEST_URL}?{'&'.join(query_parts)}"
    data = getter(url)
    parsed_list = data.get("parsed") or []

    ref_now = int(time.time()) if now_unix is None else int(now_unix)
    quotes: dict[str, dict[str, Any]] = {}

    for entry in parsed_list:
        raw_id = str(entry.get("id", "")).lower().removeprefix("0x")
        sym = id_to_symbol.get(raw_id)
        if not sym:
            continue
        price_obj = entry.get("price") or {}
        raw_price = int(price_obj["price"])
        raw_conf = int(price_obj["conf"])
        expo = int(price_obj["expo"])
        pub_time = int(price_obj["publish_time"])

        scale = math.pow(10.0, expo)
        price_usd = raw_price * scale
        conf_usd = raw_conf * scale
        if price_usd <= 0:
            raise ValueError(f"Non-positive Pyth price for {sym}: {price_usd}")

        age_sec = max(0, ref_now - pub_time)
        if age_sec > max_staleness_sec:
            raise ValueError(
                f"Stale Pyth feed for {sym}: age {age_sec}s exceeds {max_staleness_sec}s ceiling"
            )

        conf_bps = math.ceil((conf_usd / price_usd) * 10_000.0)
        quotes[sym] = {
            "symbol": sym,
            "feed_id": f"0x{raw_id}",
            "price_usd": round(price_usd, 6),
            "conf_usd": round(conf_usd, 6),
            "conf_bps": conf_bps,
            "publish_time": pub_time,
            "age_sec": age_sec,
        }

    missing = [s.strip().upper() for s in symbols if s.strip().upper() not in quotes]
    if missing:
        raise ValueError(f"Missing Pyth Hermes quotes in response: {missing}")
    return quotes


def inspect_solana_arena_wallet(
    wallet_address: str,
    *,
    rpc_url: str = SOLANA_MAINNET_RPC_URL,
    usdc_mint: str = SOLANA_USDC_MINT,
    min_arena_usd: float = 20.0,
    sol_price_usd: float | None = None,
    rpc_post: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    http_get: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Verifies a Solana Mainnet-Beta agent wallet's native SOL and SPL USDC balances
    against the Steve Capital Arena minimum funding requirement (`>= $20 USD`).
    """
    decode_base58_pubkey(wallet_address)
    addr = wallet_address.strip()
    poster = rpc_post or _default_rpc_post

    bal_resp = poster(
        rpc_url,
        {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [addr, {"commitment": "confirmed"}]},
    )
    if "error" in bal_resp:
        raise RuntimeError(f"Solana RPC getBalance error: {bal_resp['error']}")
    lamports = int((bal_resp.get("result") or {}).get("value", 0))
    sol_balance = lamports / 1_000_000_000.0

    tok_resp = poster(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "getTokenAccountsByOwner",
            "params": [
                addr,
                {"mint": usdc_mint},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
        },
    )
    if "error" in tok_resp:
        raise RuntimeError(f"Solana RPC getTokenAccountsByOwner error: {tok_resp['error']}")

    usdc_balance = 0.0
    token_accounts = (tok_resp.get("result") or {}).get("value") or []
    for acct in token_accounts:
        parsed_info = (
            ((acct.get("account") or {}).get("data") or {}).get("parsed") or {}
        ).get("info") or {}
        tok_amt = parsed_info.get("tokenAmount") or {}
        if "uiAmountString" in tok_amt and tok_amt["uiAmountString"] is not None:
            usdc_balance += float(tok_amt["uiAmountString"])
        elif "uiAmount" in tok_amt and tok_amt["uiAmount"] is not None:
            usdc_balance += float(tok_amt["uiAmount"])

    sol_conf_bps: int | None = None
    getter = http_get or _default_http_get
    if sol_price_usd is None:
        try:
            quotes = fetch_pyth_hermes_quotes(("SOL/USD",), http_get=getter)
            sol_usd = float(quotes["SOL/USD"]["price_usd"])
            sol_conf_bps = int(quotes["SOL/USD"]["conf_bps"])
            price_source = "pyth_hermes_v2"
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                raise
            spot_resp = getter(COINBASE_SOL_SPOT_URL)
            sol_usd = float(((spot_resp.get("data") or {}).get("amount")) or 0.0)
            if sol_usd <= 0:
                raise ValueError("Invalid SOL spot fallback price") from exc
            price_source = "coinbase_spot_fallback"
    else:
        if sol_price_usd <= 0:
            raise ValueError("sol_price_usd must be positive")
        sol_usd = float(sol_price_usd)
        price_source = "caller_override"

    sol_value_usd = sol_balance * sol_usd
    total_usd = round(usdc_balance + sol_value_usd, 4)
    meets_floor = total_usd >= min_arena_usd

    record = {
        "wallet_address": addr,
        "rpc_url": rpc_url,
        "sol_balance": round(sol_balance, 9),
        "sol_price_usd": round(sol_usd, 4),
        "sol_pyth_conf_bps": sol_conf_bps,
        "price_source": price_source,
        "usdc_mint": usdc_mint,
        "usdc_token_accounts": len(token_accounts),
        "usdc_balance": round(usdc_balance, 6),
        "total_arena_equity_usd": total_usd,
        "minimum_required_usd": round(min_arena_usd, 2),
        "arena_eligible": meets_floor,
        "shortfall_usd": round(max(0.0, min_arena_usd - total_usd), 4),
    }
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    record["readiness_receipt"] = f"steve:arena-check:v1:{digest[:28]}"
    return record
