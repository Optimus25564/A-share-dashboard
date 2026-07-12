#!/usr/bin/env python3
"""Fill missing US actual financial rows from SEC Companyfacts XBRL data.

This script only fills rows that are currently missing. It does not overwrite
existing sourced rows, and it only uses official SEC data.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "companies_us.json"
USER_AGENT = "rmb-invest data audit contact@example.com"
# 含 amended filings: 更正/重述值应以最新 filed 为准
ALLOWED_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "6-K", "6-K/A"}

_Q_RE = re.compile(r"^(\d{4})Q([1-4])$")


def frame_for_quarter(q: str | None) -> str | None:
    """'2026Q2' → 'CY2026Q2'; 不再用硬编码表, 任何合法标签都能映射。"""
    if not q or not _Q_RE.fullmatch(q):
        return None
    return f"CY{q}"


def window_for_quarter(q: str | None) -> tuple[date, date] | None:
    """季度标签 → 该日历季度的 (起, 止) 日期窗口 (用于按 period end 匹配财季)。"""
    m = _Q_RE.fullmatch(q or "")
    if not m:
        return None
    year, qi = int(m.group(1)), int(m.group(2))
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(year, *starts[qi]), date(year, *ends[qi])

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
    window = window_for_quarter(q)
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
    m = re.fullmatch(r"CY(\d{4})Q[1-4]", target_frame or "")
    if not m:
        return None
    year = int(m.group(1))
    annual = annual_value_by_calendar_year(entries, year)
    parts = [
        value_by_frame(entries, frame)
        for frame in (f"CY{year}Q1", f"CY{year}Q2", f"CY{year}Q3", f"CY{year}Q4")
        if frame != target_frame
    ]
    if not annual or any(part is None for part in parts):
        return None
    annual_value, annual_entry = annual
    value = annual_value - sum(part[0] for part in parts if part)
    return value, annual_entry


def derived_fiscal_year_final_quarter(entries: list[dict], q: str) -> tuple[float, dict] | None:
    window = window_for_quarter(q)
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


def next_quarter_label(q: str | None) -> str | None:
    m = _Q_RE.fullmatch(q or "")
    if not m:
        return None
    year, qi = int(m.group(1)), int(m.group(2))
    return f"{year + 1}Q1" if qi == 4 else f"{year}Q{qi + 1}"


def build_quarter_update(symbol, cik, q, revenue_entries, gross_entries,
                         cost_entries, operating_entries, net_entries):
    """按仓库口径 (period end 落在该日历季) 从 SEC facts 构建一行季度财务。找不到返回 None。"""
    frame = frame_for_quarter(q)
    if not frame:
        print(f"  ⚠ {symbol}: 季度标签 {q!r} 不合法, 无法映射 — 请检查数据")
        return None
    revenue = get_metric(revenue_entries, frame, q)
    if not revenue:
        return None
    rev_value_raw, revenue_entry, rev_derived = revenue
    # 其余指标优先取与 revenue 完全同期的值, 避免同一行混拼两个财季
    ref = None if rev_derived else revenue_entry
    gross = get_metric(gross_entries, frame, q, ref_entry=ref)
    cost = get_metric(cost_entries, frame, q, ref_entry=ref)
    operating = get_metric(operating_entries, frame, q, ref_entry=ref)
    net = get_metric(net_entries, frame, q, ref_entry=ref)
    if not net or (not gross and not cost and not operating):
        return None
    unit = revenue_entry.get("_unit", "USD")
    try:
        rev_value, fx_note = convert_to_usd(rev_value_raw, unit, q)
    except ValueError as exc:
        print(f"  ⚠ {symbol} {q}: {exc} — 补充 FX_TO_USD 表后重跑")
        return None
    if rev_value == 0:
        return None
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
            # 第二个 tag 是税前利润, 不能标成 operating income
            metric_label = ("GAAP operating income"
                            if operating_entry.get("_fact") == "OperatingIncomeLoss"
                            else "GAAP pretax income (operating income tag unavailable)")
            profitability_metric = {
                "metric": metric_label,
                "value": to_100m_usd(operating_value),
                "unit": "亿$",
                "margin_pct": pct(operating_value, rev_value),
                "derived": operating_derived,
                "basis": f"SEC Companyfacts {frame} {operating_entry.get('_fact')}",
            }
    net_value_raw, net_entry, net_derived = net
    net_value, _ = convert_to_usd(net_value_raw, net_entry.get("_unit", unit), q)
    # 只有实际用到的指标是派生值时才标注派生 (gross 可用时 operating 的派生与本行无关)
    operating_used_derived = (not gross and not cost and operating and operating[2])
    used_derived = rev_derived or (gross and gross_derived) or (not gross and cost and cost_derived) \
        or operating_used_derived or net_derived
    derived_text = ""
    if used_derived:
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
    return update


def value_by_exact_period(entries: list[dict], start: str | None, end: str | None) -> tuple[float, dict] | None:
    """与参照条目 (通常是 revenue) 完全同一 start/end 期间的值。"""
    if not start or not end:
        return None
    candidates = [
        e for e in entries
        if e.get("val") is not None and e.get("form") in ALLOWED_FORMS
        and e.get("start") == start and e.get("end") == end
    ]
    if not candidates:
        return None
    entry = sorted(candidates, key=lambda e: e.get("filed", ""))[-1]
    return float(entry["val"]), entry


def _entries_of_unit(entries: list[dict], unit: str) -> list[dict]:
    return [e for e in entries if e.get("_unit") == unit]


def get_metric(entries: list[dict], frame: str, q: str, ref_entry: dict | None = None) -> tuple[float, dict, bool] | None:
    """查找顺序 (修复财年错位公司 off-by-one):

    1. 与 revenue 完全同期 (保证同一行内各指标不跨财季混拼)
    2. period end 落在该日历季窗口 —— 这是本仓库的季度归属口径,
       对 NVDA/AVGO 等财年错位公司是唯一正确的口径
    3. SEC frame (frame 按期间中点归属, 财年错位公司会差一个季度, 只作兜底)
    4. 年度值减其它季度派生 / 财年末季 = 财年减 YTD 派生 (按同币种分组, 避免 EUR/USD 混减)
    """
    if ref_entry is not None:
        exact = value_by_exact_period(entries, ref_entry.get("start"), ref_entry.get("end"))
        if exact:
            value, entry = exact
            return value, entry, False
    period_match = value_by_period_end(entries, q)
    if period_match:
        value, entry = period_match
        return value, entry, False
    direct = value_by_frame(entries, frame)
    if direct:
        value, entry = direct
        # frame 按期间中点归属; 财年错位公司的 frame 结果可能是相邻财季 (曾造成 MRVL/CSCO 等
        # 同一财季写进两个标签的重影)。只接受结束日真的落在该标签日历季窗口内的 frame 结果。
        window = window_for_quarter(q)
        end = parse_date(entry.get("end"))
        if window and end and window[0] <= end <= window[1]:
            return value, entry, False
    for unit in ("USD", "EUR"):
        subset = _entries_of_unit(entries, unit)
        if not subset:
            continue
        derived = derived_annual_minus_other_quarters(subset, frame)
        if derived:
            value, entry = derived
            return value, entry, True
        fiscal_final_quarter = derived_fiscal_year_final_quarter(subset, q)
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
        api_ticker = "ASX" if symbol == "ASE" else symbol  # ASE 的真实 ADR ticker
        if not quarters or api_ticker not in ticker_map:
            continue

        # 注意: 不能因既有行都已填就跳过 —— 还要检查 SEC 是否披露了新财季 (追加逻辑)
        cik = ticker_map[api_ticker]
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

        # 1) 填补既有行 (src=NA / 缺值)
        for row in quarters:
            q = row.get("q")
            if not should_fill(row):
                continue
            update = build_quarter_update(symbol, cik, q, revenue_entries, gross_entries,
                                          cost_entries, operating_entries, net_entries)
            if update:
                row.update(update)
                changed += 1

        # 2) 追加 SEC 已披露但本地还没有的新财季 (最多前进 3 季)
        for _ in range(3):
            last_row = quarters[-1]
            nq = next_quarter_label(last_row.get("q"))
            if not nq:
                break
            update = build_quarter_update(symbol, cik, nq, revenue_entries, gross_entries,
                                          cost_entries, operating_entries, net_entries)
            if not update:
                break
            # 防重复守卫: 财季结束日贴日历季边界的公司 (如 SNDK 4/3 结束),
            # frame 口径的旧行和结束日口径的新行可能是同一个财季 — rev/gm/nm 全等则视为重复
            if (update.get("rev") == last_row.get("rev")
                    and update.get("gm") == last_row.get("gm")
                    and update.get("nm") == last_row.get("nm")):
                print(f"  ⚠ {symbol}: {nq} 与上一行数值完全相同, 疑似同一财季的口径重影, 跳过追加")
                break
            quarters.append({"q": nq, **update})
            print(f"  + {symbol}: 追加新财季 {nq} (rev {update['rev']} 亿$, GM {update['gm']}%)")
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
