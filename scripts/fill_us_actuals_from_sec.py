#!/usr/bin/env python3
"""Fill missing US actual financial rows from SEC Companyfacts XBRL data.

This script only fills rows that are currently missing. It does not overwrite
existing sourced rows, and it only uses official SEC data.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "companies_us.json"
USER_AGENT = "rmb-invest data audit contact@example.com"
ALLOWED_FORMS = {"10-Q", "10-K", "20-F", "6-K"}

QUARTER_TO_FRAME = {
    "2025Q1": "CY2025Q1",
    "2025Q2": "CY2025Q2",
    "2025Q3": "CY2025Q3",
    "2025Q4": "CY2025Q4",
    "2026Q1": "CY2026Q1",
}

QUARTER_END_RANGES = {
    "2025Q1": (date(2025, 1, 1), date(2025, 3, 31)),
    "2025Q2": (date(2025, 4, 1), date(2025, 6, 30)),
    "2025Q3": (date(2025, 7, 1), date(2025, 9, 30)),
    "2025Q4": (date(2025, 10, 1), date(2025, 12, 31)),
    "2026Q1": (date(2026, 1, 1), date(2026, 3, 31)),
}

# Quarterly average EUR/USD rates. Used only for SEC facts reported in EUR,
# and always disclosed in the row note.
FX_TO_USD = {
    ("EUR", "2025Q1"): 1.052,
    ("EUR", "2025Q2"): 1.134,
    ("EUR", "2025Q3"): 1.168,
    ("EUR", "2025Q4"): 1.165,
    ("EUR", "2026Q1"): 1.099,
}

REVENUE_FACTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
)

COST_FACTS = (
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
    "CostOfServices",
    "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
)

OPERATING_INCOME_FACTS = (
    "OperatingIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def load_ticker_map() -> dict[str, int]:
    raw = fetch_json("https://www.sec.gov/files/company_tickers.json")
    return {item["ticker"].upper(): item["cik_str"] for item in raw.values()}


def fact_entries(facts: dict, fact_names: tuple[str, ...]) -> list[dict]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    entries = []
    for name in fact_names:
        units = us_gaap.get(name, {}).get("units", {})
        if "USD" in units:
            for entry in units["USD"]:
                copied = dict(entry)
                copied["_fact"] = name
                copied["_unit"] = "USD"
                entries.append(copied)
        if "EUR" in units:
            for entry in units["EUR"]:
                copied = dict(entry)
                copied["_fact"] = name
                copied["_unit"] = "EUR"
                entries.append(copied)
    return entries


def entry_by_frame(entries: list[dict], frame: str) -> dict | None:
    candidates = [
        e for e in entries
        if e.get("frame") == frame and e.get("val") is not None and e.get("form") in ALLOWED_FORMS
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda e: e.get("filed", ""))[-1]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def entry_by_period_end(entries: list[dict], q: str) -> dict | None:
    window = QUARTER_END_RANGES.get(q)
    if not window:
        return None
    start_window, end_window = window
    candidates = []
    for entry in entries:
        if entry.get("val") is None or entry.get("form") not in ALLOWED_FORMS:
            continue
        start = parse_date(entry.get("start"))
        end = parse_date(entry.get("end"))
        if not start or not end or not (start_window <= end <= end_window):
            continue
        duration = (end - start).days
        if 60 <= duration <= 120:
            candidates.append(entry)
    if not candidates:
        return None
    return sorted(candidates, key=lambda e: (e.get("filed", ""), e.get("end", "")))[-1]


def value_by_frame(entries: list[dict], frame: str) -> tuple[float, dict] | None:
    entry = entry_by_frame(entries, frame)
    if not entry:
        return None
    return float(entry["val"]), entry


def value_by_period_end(entries: list[dict], q: str) -> tuple[float, dict] | None:
    entry = entry_by_period_end(entries, q)
    if not entry:
        return None
    return float(entry["val"]), entry


def annual_value_by_calendar_year(entries: list[dict], year: int) -> tuple[float, dict] | None:
    direct = value_by_frame(entries, f"CY{year}")
    if direct:
        return direct
    candidates = []
    for entry in entries:
        if entry.get("val") is None or entry.get("form") not in ALLOWED_FORMS:
            continue
        start = parse_date(entry.get("start"))
        end = parse_date(entry.get("end"))
        if start == date(year, 1, 1) and end == date(year, 12, 31):
            candidates.append(entry)
    if not candidates:
        return None
    entry = sorted(candidates, key=lambda e: e.get("filed", ""))[-1]
    return float(entry["val"]), entry


def derived_annual_minus_other_quarters(entries: list[dict], target_frame: str) -> tuple[float, dict] | None:
    if target_frame not in {"CY2025Q1", "CY2025Q2", "CY2025Q3", "CY2025Q4"}:
        return None
    annual = annual_value_by_calendar_year(entries, 2025)
    parts = [
        value_by_frame(entries, frame)
        for frame in ("CY2025Q1", "CY2025Q2", "CY2025Q3", "CY2025Q4")
        if frame != target_frame
    ]
    if not annual or any(part is None for part in parts):
        return None
    annual_value, annual_entry = annual
    value = annual_value - sum(part[0] for part in parts if part)
    return value, annual_entry


def derived_fiscal_year_final_quarter(entries: list[dict], q: str) -> tuple[float, dict] | None:
    window = QUARTER_END_RANGES.get(q)
    if not window:
        return None
    start_window, end_window = window
    candidates = []
    for annual in entries:
        if annual.get("val") is None or annual.get("form") not in ALLOWED_FORMS:
            continue
        annual_start = parse_date(annual.get("start"))
        annual_end = parse_date(annual.get("end"))
        if not annual_start or not annual_end or not (start_window <= annual_end <= end_window):
            continue
        if not 300 <= (annual_end - annual_start).days <= 380:
            continue
        ytd_parts = []
        for part in entries:
            if part.get("val") is None or part.get("form") not in ALLOWED_FORMS:
                continue
            part_start = parse_date(part.get("start"))
            part_end = parse_date(part.get("end"))
            if part_start != annual_start or not part_end or not (annual_start < part_end < annual_end):
                continue
            duration = (part_end - part_start).days
            if 240 <= duration <= 300:
                ytd_parts.append(part)
        if ytd_parts:
            ytd = sorted(ytd_parts, key=lambda e: (e.get("end", ""), e.get("filed", "")))[-1]
            candidates.append((float(annual["val"]) - float(ytd["val"]), annual))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[1].get("filed", ""))[-1]


def filing_url(cik: int, accn: str | None) -> str:
    if not accn:
        return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{accn}-index.html"


def to_100m_usd(value: float) -> float:
    return round(value / 100_000_000, 1)


def pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 2)


def convert_to_usd(value: float, unit: str, q: str) -> tuple[float, str]:
    if unit == "USD":
        return value, ""
    rate = FX_TO_USD.get((unit, q))
    if not rate:
        raise ValueError(f"missing FX rate for {unit} {q}")
    return value * rate, f" {unit}/USD avg rate {rate:.3f};"


def should_fill(row: dict) -> bool:
    if row.get("src") == "A" and row.get("source_url"):
        return False
    return any(row.get(k) is None for k in ("rev", "gm", "nm")) or row.get("src") == "NA"


def get_metric(entries: list[dict], frame: str, q: str) -> tuple[float, dict, bool] | None:
    direct = value_by_frame(entries, frame)
    if direct:
        value, entry = direct
        return value, entry, False
    period_match = value_by_period_end(entries, q)
    if period_match:
        value, entry = period_match
        return value, entry, False
    derived = derived_annual_minus_other_quarters(entries, frame)
    if derived:
        value, entry = derived
        return value, entry, True
    fiscal_final_quarter = derived_fiscal_year_final_quarter(entries, q)
    if fiscal_final_quarter:
        value, entry = fiscal_final_quarter
        return value, entry, True
    return None


def main() -> int:
    data = json.loads(DATA_PATH.read_text())
    ticker_map = load_ticker_map()
    changed = 0
    skipped = []

    for symbol, company in data.items():
        if symbol.startswith("_") or not isinstance(company, dict):
            continue
        quarters = company.get("quarters") or []
        if not quarters or symbol not in ticker_map:
            continue

        if all(not should_fill(row) for row in quarters):
            continue

        cik = ticker_map[symbol]
        try:
            facts = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        except Exception as exc:
            skipped.append((symbol, f"fetch_failed:{exc}"))
            continue
        time.sleep(0.12)

        revenue_entries = fact_entries(facts, REVENUE_FACTS)
        gross_entries = fact_entries(facts, ("GrossProfit",))
        cost_entries = fact_entries(facts, COST_FACTS)
        net_entries = fact_entries(facts, ("NetIncomeLoss", "ProfitLoss"))
        operating_entries = fact_entries(facts, OPERATING_INCOME_FACTS)
        if not revenue_entries or not net_entries or (not gross_entries and not cost_entries and not operating_entries):
            skipped.append((symbol, "missing_required_sec_facts"))
            continue

        for row in quarters:
            q = row.get("q")
            frame = QUARTER_TO_FRAME.get(q)
            if not frame or not should_fill(row):
                continue
            revenue = get_metric(revenue_entries, frame, q)
            gross = get_metric(gross_entries, frame, q)
            cost = get_metric(cost_entries, frame, q)
            operating = get_metric(operating_entries, frame, q)
            net = get_metric(net_entries, frame, q)
            if not revenue or not net or (not gross and not cost and not operating):
                continue
            rev_value_raw, revenue_entry, rev_derived = revenue
            unit = revenue_entry.get("_unit", "USD")
            rev_value, fx_note = convert_to_usd(rev_value_raw, unit, q)
            if rev_value == 0:
                continue
            profitability_metric = None
            cost_derived = False
            if gross:
                gross_value_raw, gross_entry, gross_derived = gross
                gross_value, _ = convert_to_usd(gross_value_raw, gross_entry.get("_unit", unit), q)
                gross_note = f"gross profit ${gross_value/1_000_000_000:.3f}B"
            else:
                gross_derived = False
                if cost:
                    cost_value_raw, cost_entry, cost_derived = cost
                    cost_value, _ = convert_to_usd(cost_value_raw, cost_entry.get("_unit", unit), q)
                    gross_value = rev_value - cost_value
                    gross_note = (
                        f"gross profit ${gross_value/1_000_000_000:.3f}B "
                        f"(revenue minus {cost_entry.get('_fact')} ${cost_value/1_000_000_000:.3f}B)"
                    )
                else:
                    operating_value_raw, operating_entry, operating_derived = operating
                    operating_value, _ = convert_to_usd(operating_value_raw, operating_entry.get("_unit", unit), q)
                    gross_value = None
                    gross_note = "gross profit not available in standard SEC Companyfacts tags"
                    profitability_metric = {
                        "metric": "GAAP operating income",
                        "value": to_100m_usd(operating_value),
                        "unit": "亿$",
                        "margin_pct": pct(operating_value, rev_value),
                        "derived": operating_derived,
                        "basis": f"SEC Companyfacts {frame} {operating_entry.get('_fact')}",
                    }
            net_value_raw, net_entry, net_derived = net
            net_value, _ = convert_to_usd(net_value_raw, net_entry.get("_unit", unit), q)
            derived_text = ""
            if rev_derived or (gross and gross_derived) or (cost and cost_derived) or (operating and operating[2]) or net_derived:
                derived_text = f" derived from SEC annual value minus other official period values to obtain {frame};"
            update = {
                "rev": to_100m_usd(rev_value),
                "gm": pct(gross_value, rev_value) if gross_value is not None else None,
                "nm": pct(net_value, rev_value),
                "src": "A",
                "source_url": filing_url(cik, revenue_entry.get("accn")),
                "note": (
                    f"SEC Companyfacts {frame}:{derived_text}{fx_note} revenue ${rev_value/1_000_000_000:.3f}B, "
                    f"{gross_note}, "
                    f"net income ${net_value/1_000_000_000:.3f}B"
                ),
            }
            if profitability_metric:
                update["profitability_metric"] = profitability_metric
            row.update(update)
            changed += 1

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Filled {changed} missing US actual rows from SEC Companyfacts.")
    if skipped:
        print("Skipped:")
        for symbol, reason in skipped:
            print(f"  {symbol}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
