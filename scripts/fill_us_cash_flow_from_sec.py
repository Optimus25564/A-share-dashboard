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
    # 注意: 不要加 PaymentsToAcquireBusinessesAndInterestInAffiliates —— 那是并购支出, 不是 capex
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
]
REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "Revenue",
]
SHORT_TERM_DEBT_TAGS = [
    "ShortTermBorrowings",
    "CommercialPaper",
    "OtherShortTermBorrowings",
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


ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
INSTANT_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A"}


def _days_between(start: str, end: str) -> int | None:
    try:
        from datetime import date
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        return (e - s).days
    except Exception:
        return None


def latest_annual_fact(facts: dict, tags: list[str], fx: dict) -> tuple[float | None, dict | None, str | None, str | None]:
    """选取最近一个完整财年的年度值。

    关键点 (修复 FY2023 陈旧数据 bug):
    - 10-K/20-F 会同时申报 2-3 个对比财年, filed 日期相同 → 不能只按 filed 选,
      必须优先比较 period end, 否则会拿到最旧的对比年份。
    - 必须校验 duration ≈ 一个财年 (340-395 天), 排除季度/YTD 值。
    """
    best = None
    best_tag = None
    best_unit = None
    for tag in tags:
        for unit, item in facts_for_tag(facts, tag):
            if item.get("form") not in ANNUAL_FORMS:
                continue
            if item.get("fp") != "FY":
                continue
            if not item.get("filed") or item.get("val") is None:
                continue
            start, end = item.get("start"), item.get("end")
            if not start or not end:
                continue
            days = _days_between(start, end)
            if days is None or not (340 <= days <= 395):
                continue
            key = (end, item["filed"])
            if best is None or key > (best["end"], best["filed"]):
                best = item
                best_tag = tag
                best_unit = unit
    if not best:
        return None, None, None, None
    usd = to_usd_billion(float(best["val"]), best_unit or "USD", fx)
    meta = {"filed": best.get("filed"), "start": best.get("start"), "end": best.get("end")}
    return usd, meta, best_tag, best_unit


def latest_instant_fact(facts: dict, tags: list[str], fx: dict) -> tuple[float | None, dict | None, str | None, str | None]:
    """选取最近一个资产负债表日的 instant 值 (按 period end 优先, 而非 filed)。"""
    best = None
    best_tag = None
    best_unit = None
    for tag in tags:
        for unit, item in facts_for_tag(facts, tag):
            if item.get("form") not in INSTANT_FORMS:
                continue
            if not item.get("filed") or item.get("val") is None:
                continue
            end = item.get("end")
            if not end:
                continue
            key = (end, item["filed"])
            if best is None or key > (best["end"], best["filed"]):
                best = item
                best_tag = tag
                best_unit = unit
    if not best:
        return None, None, None, None
    usd = to_usd_billion(float(best["val"]), best_unit or "USD", fx)
    meta = {"filed": best.get("filed"), "end": best.get("end")}
    return usd, meta, best_tag, best_unit


def annual_fact_for_period(facts: dict, tags: list[str], fx: dict, end: str) -> tuple[float | None, str | None]:
    """取与指定财年 end 相同期间的年度值 (用于 CapEx/收入与 OCF 同财年配对)。"""
    for tag in tags:
        for unit, item in facts_for_tag(facts, tag):
            if item.get("form") not in ANNUAL_FORMS or item.get("fp") != "FY":
                continue
            if item.get("val") is None or item.get("end") != end:
                continue
            start = item.get("start")
            days = _days_between(start, end) if start else None
            if days is None or not (340 <= days <= 395):
                continue
            return to_usd_billion(float(item["val"]), unit or "USD", fx), tag
    return None, None


def is_stale(end: str | None, reference_end: str | None, months: int = 15) -> bool:
    """instant 值的 period end 落后于参照日期超过 N 个月 → 视为陈旧不可用。"""
    if not end or not reference_end:
        return False
    days = _days_between(end, reference_end)
    return days is not None and days > months * 30


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
        # 手工录入的公司 (如 GLW: SEC XBRL 缺标准 capex tag) 不被自动覆盖
        if (company.get("quality_metrics") or {}).get("manual_override"):
            print(f"  ℹ {ticker}: quality_metrics 为手工录入 (manual_override), 跳过自动填充")
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

        ocf, ocf_meta, ocf_tag, ocf_unit = latest_annual_fact(facts, OPERATING_CASH_FLOW_TAGS, fx)
        capex, capex_meta, capex_tag, capex_unit = latest_annual_fact(facts, CAPEX_TAGS, fx)
        cash, cash_meta, cash_tag, cash_unit = latest_instant_fact(facts, CASH_TAGS, fx)
        debt, debt_meta, debt_tag, debt_unit = latest_instant_fact(facts, LONG_TERM_DEBT_TAGS, fx)
        st_debt, st_meta, st_tag, _ = latest_instant_fact(facts, SHORT_TERM_DEBT_TAGS, fx)

        # 时效守卫: OCF 和 CapEx 必须来自同一财年, 否则 FCF 是错配的
        ocf_end = ocf_meta.get("end") if ocf_meta else None
        capex_end = capex_meta.get("end") if capex_meta else None
        if ocf is not None and capex is not None and ocf_end != capex_end:
            paired, paired_tag = annual_fact_for_period(facts, CAPEX_TAGS, fx, ocf_end) if ocf_end else (None, None)
            if paired is not None:
                capex = paired
                capex_tag = paired_tag
                capex_meta = dict(ocf_meta)
            else:
                print(f"  ⚠ {ticker}: OCF 财年 ({ocf_end}) 与 CapEx 财年 ({capex_end}) 不一致且无法配对, 丢弃 CapEx/FCF")
                capex = None
        # 债务/现金的资产负债表日不得比现金流财年末陈旧超过 15 个月 (防止 2013 年的 tag 残留)
        cash_end = cash_meta.get("end") if cash_meta else None
        if debt is not None and is_stale(debt_meta.get("end") if debt_meta else None, cash_end or ocf_end):
            print(f"  ⚠ {ticker}: 债务数据陈旧 (end={debt_meta.get('end')}), 置空")
            debt = None
        # 短债只有与长债同一资产负债表日才可加总 (避免跨期错配)
        if st_debt is not None and (debt is None or (st_meta or {}).get("end") != (debt_meta or {}).get("end")):
            st_debt = None
        if ocf is not None and ocf_end:
            from datetime import date
            age_days = _days_between(ocf_end, date.today().isoformat())
            if age_days is not None and age_days > 540:
                print(f"  ⚠ {ticker}: 最新年度现金流截至 {ocf_end}, 已超过 18 个月")

        metrics = company.get("quality_metrics", {})
        metrics["source"] = "SEC Companyfacts"
        metrics["source_url"] = sec_companyfacts_url(cik)
        metrics["fx_source"] = "https://open.er-api.com/v6/latest/USD"
        metrics["fx_mode"] = "spot_at_run"  # 非美元报表按运行日即期汇率换算, 见 _meta 说明
        metrics["cik"] = cik
        metrics["ticker_for_sec"] = api_ticker

        # 取不到新值时必须清掉旧 key, 不能让上一轮的陈旧数值残留
        if ocf is None:
            for k in ["operating_cash_flow_billion", "operating_cash_flow_filed",
                      "operating_cash_flow_period", "operating_cash_flow_tag",
                      "operating_cash_flow_unit"]:
                metrics.pop(k, None)
        if capex is None:
            for k in ["capex_billion", "capex_filed", "capex_period", "capex_tag", "capex_unit"]:
                metrics.pop(k, None)
        if ocf is None or capex is None:
            for k in ["free_cash_flow_billion", "fcf_margin_pct", "fcf_margin_basis"]:
                metrics.pop(k, None)
        if cash is None:
            for k in ["cash_billion", "cash_filed", "cash_end", "cash_tag", "cash_unit"]:
                metrics.pop(k, None)

        if ocf is not None:
            metrics["operating_cash_flow_billion"] = round(ocf, 3)
            metrics["operating_cash_flow_filed"] = ocf_meta.get("filed")
            metrics["operating_cash_flow_period"] = f"{ocf_meta.get('start')} → {ocf_meta.get('end')}"
            metrics["operating_cash_flow_tag"] = ocf_tag
            metrics["operating_cash_flow_unit"] = ocf_unit
        if capex is not None:
            metrics["capex_billion"] = round(abs(capex), 3)
            metrics["capex_filed"] = capex_meta.get("filed")
            metrics["capex_period"] = f"{capex_meta.get('start')} → {capex_meta.get('end')}"
            metrics["capex_tag"] = capex_tag
            metrics["capex_unit"] = capex_unit
        if ocf is not None and capex is not None:
            fcf = ocf - abs(capex)
            metrics["free_cash_flow_billion"] = round(fcf, 3)
            metrics["fcf_margin_pct"] = None
            # FCF margin 用同一财年的 SEC 收入配对 (分子分母同期); 找不到才回退 TTM quarters
            fy_rev, _ = annual_fact_for_period(facts, REVENUE_TAGS, fx, ocf_end) if ocf_end else (None, None)
            if fy_rev and fy_rev > 0:
                metrics["fcf_margin_pct"] = round(fcf / fy_rev * 100, 2)
                metrics["fcf_margin_basis"] = f"FY rev {ocf_meta.get('start')} → {ocf_end} (SEC)"
            else:
                qs = company.get("quarters") or []
                finite = [q["rev"] for q in qs if q.get("rev") is not None]
                if len(finite) >= 4:
                    # Dashboard US revenue unit is $100M; SEC cash-flow unit here is $1B.
                    ttm_rev = sum(finite[-4:]) / 10
                    if ttm_rev > 0:
                        metrics["fcf_margin_pct"] = round(fcf / ttm_rev * 100, 2)
                        metrics["fcf_margin_basis"] = "TTM quarters (口径警告: FCF 为上一完整财年)"
        if cash is not None:
            metrics["cash_billion"] = round(cash, 3)
            metrics["cash_filed"] = cash_meta.get("filed")
            metrics["cash_end"] = cash_meta.get("end")
            metrics["cash_tag"] = cash_tag
            metrics["cash_unit"] = cash_unit
        if debt is not None:
            total_debt = debt + (st_debt or 0)
            metrics["long_term_debt_billion"] = round(debt, 3)
            metrics["long_term_debt_filed"] = debt_meta.get("filed")
            metrics["long_term_debt_end"] = debt_meta.get("end")
            metrics["long_term_debt_tag"] = debt_tag
            metrics["long_term_debt_unit"] = debt_unit
            if st_debt is not None:
                metrics["short_term_debt_billion"] = round(st_debt, 3)
                metrics["short_term_debt_tag"] = st_tag
            metrics["debt_billion"] = round(total_debt, 3)
        else:
            # 陈旧/缺失的债务必须显式清掉旧值, 不能让上一轮的错误残留
            for k in ["long_term_debt_billion", "long_term_debt_filed", "long_term_debt_end",
                      "long_term_debt_tag", "long_term_debt_unit", "short_term_debt_billion",
                      "short_term_debt_tag", "debt_billion", "net_cash_billion"]:
                metrics.pop(k, None)
        if cash is not None and debt is not None:
            metrics["net_cash_billion"] = round(cash - (debt + (st_debt or 0)), 3)

        company["quality_metrics"] = metrics
        updated += 1
        time.sleep(0.12)

    meta = companies.setdefault("_meta", {})
    meta["quality_metrics_policy"] = (
        "OCF/CapEx/FCF/cash/debt are sourced from SEC Companyfacts when available. "
        "FCF = latest-full-fiscal-year OCF - same-fiscal-year capex (period recorded in *_period). "
        "Balance-sheet items use the latest period end; debt older than 15 months vs cash is dropped. "
        "Non-USD facts are converted at the spot rate on the run date (fx_mode=spot_at_run) — "
        "historical-period flows therefore carry FX drift. Missing values mean no acceptable "
        "SEC Companyfacts fact was found and must not be inferred."
    )
    DATA_PATH.write_text(json.dumps(companies, ensure_ascii=False, indent=2) + "\n")
    print(f"updated {updated} companies")
    if missing:
        print("missing:")
        for item in missing:
            print(f"  {item[0]}: {item[1]}")


if __name__ == "__main__":
    main()
