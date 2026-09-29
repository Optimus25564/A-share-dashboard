#!/usr/bin/env python3
"""Build static market-data files from Futunn's gateway-free REST API."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


API_BASE = "https://webapi.futunn.com"
PERIODS = {"day": 2, "week": 3, "month": 4}


def request_json(url: str, *, method: str = "GET", body=None, headers=None):
    encoded = None
    request_headers = dict(headers or {})
    if body is not None:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=encoded, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Futunn HTTP {exc.code}: {detail}") from exc


def access_token(client_id: str, refresh_token: str) -> str:
    form = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
    ).encode()
    req = urllib.request.Request(
        f"{API_BASE}/oauth2/token",
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Futunn token refresh failed ({exc.code}): {detail}") from exc
    token = result.get("access_token")
    if not token:
        raise RuntimeError("Futunn token refresh returned no access_token")
    return token


def symbol_for(code: str, market: str) -> str:
    if market == "US":
        aliases = {"ASE": "ASX"}
        return f"US.{aliases.get(code, code)}"
    if code.startswith("6"):
        return f"SH.{code}"
    if code.startswith(("4", "8", "9")):
        return f"BJ.{code}"
    return f"SZ.{code}"


def load_symbols(repo: Path) -> dict[str, str]:
    result = {"__SH_INDEX": "SH.000001", "__QQQ": "US.QQQ"}
    for filename, market in (("companies.json", "CN"), ("companies_us.json", "US")):
        with (repo / "data" / filename).open(encoding="utf-8") as handle:
            companies = json.load(handle)
        for code in companies:
            if not code.startswith("_"):
                result[code] = symbol_for(code, market)
    return result


def futu_call(path: str, token: str, *, method="GET", body=None):
    result = request_json(
        f"{API_BASE}{path}",
        method=method,
        body=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    if result.get("ret_code") != 0:
        raise RuntimeError(f"Futunn API error {result.get('ret_code')}: {result.get('ret_msg')}")
    return result.get("data") or {}


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def refresh_snapshot(repo: Path, token: str, symbols: dict[str, str]) -> None:
    data = futu_call(
        "/api/v1.0/quote/snapshot",
        token,
        method="POST",
        body={"code_list": list(symbols.values())},
    )
    by_symbol = {item["code"]: item for item in data.get("snapshot_list", [])}
    quotes = {code: by_symbol[symbol] for code, symbol in symbols.items() if symbol in by_symbol}
    atomic_json(
        repo / "data" / "futu_snapshot.json",
        {
            "_meta": {
                "source": "Futunn OpenAPI REST",
                "updated_at_ms": int(time.time() * 1000),
                "requested": len(symbols),
                "returned": len(quotes),
            },
            "quotes": quotes,
        },
    )
    print(f"Snapshot: {len(quotes)}/{len(symbols)} symbols")


def refresh_klines(repo: Path, token: str, symbols: dict[str, str]) -> None:
    end = date.today().isoformat()
    total = len(symbols) * len(PERIODS)
    completed = 0
    for code, symbol in symbols.items():
        for period, ktype in PERIODS.items():
            query = urllib.parse.urlencode({"end": end, "ktype": ktype, "autype": 1, "num": 370})
            encoded_symbol = urllib.parse.quote(symbol, safe=".")
            data = futu_call(f"/api/v1.0/quote/{encoded_symbol}/history-kline?{query}", token)
            bars = data.get("kline_list", [])
            atomic_json(
                repo / "data" / "futu_klines" / f"{symbol}.{period}.json",
                {
                    "_meta": {"source": "Futunn OpenAPI REST", "symbol": symbol, "period": period},
                    "bars": bars,
                },
            )
            completed += 1
            if completed % 20 == 0 or completed == total:
                print(f"K-lines: {completed}/{total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    client_id = os.environ.get("FUTU_CLIENT_ID")
    refresh = os.environ.get("FUTU_REFRESH_TOKEN")
    if not client_id or not refresh:
        raise SystemExit("FUTU_CLIENT_ID and FUTU_REFRESH_TOKEN are required")
    token = access_token(client_id, refresh)
    symbols = load_symbols(args.repo)
    refresh_snapshot(args.repo, token, symbols)
    if not args.snapshot_only:
        refresh_klines(args.repo, token, symbols)


if __name__ == "__main__":
    main()
