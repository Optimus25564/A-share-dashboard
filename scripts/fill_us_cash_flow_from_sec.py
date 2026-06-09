#!/usr/bin/env python3
"""Fill US cash-flow quality metrics from SEC Companyfacts.

The script adds a `quality_metrics` block to companies_us.json using only
official SEC XBRL facts. Values are stored in USD billions.
"""

from __future__ import annotations

import json
import gzip
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "companies_us.json"
SEC_HEADERS = {
    "User-Agent": "rmb-invest-dashboard data audit contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


OPERATING_CASH_FLOW_TAGS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "CashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInOperations",
]
CAPEX_TAGS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsToAcquireBusinessesAndInterestInAffiliates",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
]
LONG_TERM_DEBT_TAGS = [
    "LongTermDebtAndFinanceLeaseObligationsCurrentAndNoncurrent",
    "LongTermDebtAndFinanceLeaseObligations",
    "LongTermDebtCurrentAndNoncurrent",
    "LongTermDebt",
]
CASH_TAGS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashAndCashEquivalents",
]


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=SEC_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def sec_ticker_map() -> dict[str, str]:
    data = fetch_json("https://www.sec.gov/files/company_tickers.json")
    out = {}
    for item in data.values():
        ticker = str(item["ticker"]).upper()
        cik = str(item["cik_str"]).zfill(10)
        out[ticker] = cik
    return out


def fx_rates_per_usd() -> dict:
    data = fetch_json("https://open.er-api.com/v6/latest/USD")
    rates = data.get("rates", {})
    out = {"USD": 1.0}
    for code in ["EUR", "TWD", "CAD", "GBP", "JPY", "KRW"]:
        if code in rates and rates[code]:
            out[code] = float(rates[code])
    return out


def to_usd_billion(value: float, unit: str, fx: dict) -> float | None:
    currency = unit.split("/")[0]
    if currency not in fx:
        return None
    return float(value) / fx[currency] / 1e9


def facts_for_tag(facts: dict, tag: str) -> list[tuple[str, dict]]:
    out = []
    for namespace in facts.get("facts", {}).values():
        fact = namespace.get(tag)
        if not fact:
            continue
        for unit, items in fact.get("units", {}).items():
            if unit.split("/")[0] in {"USD", "EUR", "TWD", "CAD", "GBP", "JPY", "KRW"}:
                out.extend((unit, item) for item in items)
    return out


def latest_annual_fact(facts: dict, tags: list[str], fx: dict) -> tuple[float | None, str | None, str | None, str | None]:
    best = None
    best_tag = None
    best_unit = None
    for tag in tags:
        for unit, item in facts_for_tag(facts, tag):
            if item.get("form") not in {"10-K", "20-F", "40-F"}:
                continue
            if item.get("fp") != "FY":
                continue
            if not item.get("filed") or item.get("val") is None:
                continue
            if best is None or item["filed"] > best["filed"]:
                best = item
                best_tag = tag
                best_unit = unit
    if not best:
        return None, None, None, None
    usd = to_usd_billion(float(best["val"]), best_unit or "USD", fx)
    return usd, best.get("filed"), best_tag, best_unit


def latest_instant_fact(facts: dict, tags: list[str], fx: dict) -> tuple[float | None, str | None, str | None, str | None]:
    best = None
    best_tag = None
    best_unit = None
    for tag in tags:
        for unit, item in facts_for_tag(facts, tag):
            if item.get("form") not in {"10-K", "10-Q", "20-F", "40-F"}:
                continue
            if not item.get("filed") or item.get("val") is None:
                continue
            if best is None or item["filed"] > best["filed"]:
                best = item
                best_tag = tag
                best_unit = unit
    if not best:
        return None, None, None, None
    usd = to_usd_billion(float(best["val"]), best_unit or "USD", fx)
    return usd, best.get("filed"), best_tag, best_unit


def sec_companyfacts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def main() -> None:
    companies = json.loads(DATA_PATH.read_text())
    ticker_to_cik = sec_ticker_map()
    fx = fx_rates_per_usd()
    updated = 0
    missing = []

    for ticker, company in companies.items():
        if ticker.startswith("_"):
            continue
        api_ticker = "ASX" if ticker == "ASE" else ticker
        cik = ticker_to_cik.get(api_ticker.upper())
        if not cik:
            missing.append((ticker, "no SEC CIK mapping"))
            continue
        try:
            facts = fetch_json(sec_companyfacts_url(cik))
        except Exception as exc:
            missing.append((ticker, f"SEC fetch failed: {exc}"))
            time.sleep(0.2)
            continue

        ocf, ocf_filed, ocf_tag, ocf_unit = latest_annual_fact(facts, OPERATING_CASH_FLOW_TAGS, fx)
        capex, capex_filed, capex_tag, capex_unit = latest_annual_fact(facts, CAPEX_TAGS, fx)
        cash, cash_filed, cash_tag, cash_unit = latest_instant_fact(facts, CASH_TAGS, fx)
        debt, debt_filed, debt_tag, debt_unit = latest_instant_fact(facts, LONG_TERM_DEBT_TAGS, fx)

        metrics = company.get("quality_metrics", {})
        metrics["source"] = "SEC Companyfacts"
        metrics["source_url"] = sec_companyfacts_url(cik)
        metrics["fx_source"] = "https://open.er-api.com/v6/latest/USD"
        metrics["cik"] = cik
        metrics["ticker_for_sec"] = api_ticker

        if ocf is not None:
            metrics["operating_cash_flow_billion"] = round(ocf, 3)
            metrics["operating_cash_flow_filed"] = ocf_filed
            metrics["operating_cash_flow_tag"] = ocf_tag
            metrics["operating_cash_flow_unit"] = ocf_unit
        if capex is not None:
            metrics["capex_billion"] = round(abs(capex), 3)
            metrics["capex_filed"] = capex_filed
            metrics["capex_tag"] = capex_tag
            metrics["capex_unit"] = capex_unit
        if ocf is not None and capex is not None:
            metrics["free_cash_flow_billion"] = round(ocf - abs(capex), 3)
            metrics["fcf_margin_pct"] = None
            qs = company.get("quarters") or []
            annualized_rev = None
            if qs and qs[-1].get("rev") is not None:
                # Dashboard US revenue unit is $100M; SEC cash-flow unit here is $1B.
                annualized_rev = float(qs[-1]["rev"]) / 10 * 4
            if annualized_rev and annualized_rev > 0:
                metrics["fcf_margin_pct"] = round((ocf - abs(capex)) / annualized_rev * 100, 2)
        if cash is not None:
            metrics["cash_billion"] = round(cash, 3)
            metrics["cash_filed"] = cash_filed
            metrics["cash_tag"] = cash_tag
            metrics["cash_unit"] = cash_unit
        if debt is not None:
            metrics["long_term_debt_billion"] = round(debt, 3)
            metrics["long_term_debt_filed"] = debt_filed
            metrics["long_term_debt_tag"] = debt_tag
            metrics["long_term_debt_unit"] = debt_unit
        if cash is not None and debt is not None:
            metrics["net_cash_billion"] = round(cash - debt, 3)

        company["quality_metrics"] = metrics
        updated += 1
        time.sleep(0.12)

    meta = companies.setdefault("_meta", {})
    meta["quality_metrics_policy"] = (
        "OCF/CapEx/FCF/cash/debt are sourced from SEC Companyfacts when available. "
        "FCF = annual operating cash flow - annual capex. Missing values mean no SEC "
        "Companyfacts mapping/tag was found and must not be inferred."
    )
    DATA_PATH.write_text(json.dumps(companies, ensure_ascii=False, indent=2) + "\n")
    print(f"updated {updated} companies")
    if missing:
        print("missing:")
        for item in missing:
            print(f"  {item[0]}: {item[1]}")


if __name__ == "__main__":
    main()
