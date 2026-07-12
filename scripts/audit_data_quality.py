#!/usr/bin/env python3
"""Audit dashboard data quality.

This script does not prove that every number is correct. It checks whether the
repo has enough provenance to make each number auditable.
"""
import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]

COMPANY_FILES = [
    ("A-share", ROOT / "data" / "companies.json"),
    ("US", ROOT / "data" / "companies_us.json"),
]

STATE_FILES = [
    ("A-share", ROOT / "data" / "alerts_state.json"),
    ("US", ROOT / "data" / "alerts_state_us.json"),
]

DISALLOWED_SOURCE_DOMAINS = {
    # 政策: 二手来源只能用于发现线索, 不能作为最终财务数据来源
    "stockanalysis.com",
    "finance.yahoo.com",
    "seekingalpha.com",
    "marketwatch.com",
    "fool.com",
    "investing.com",
    "barrons.com",
    "benzinga.com",
    "zacks.com",
    "tipranks.com",
    "simplywall.st",
    "macrotrends.net",
    "wsj.com",
    "companiesmarketcap.com",
    "stocktwits.com",
    "reddit.com",
    "wikipedia.org",
    "gurufocus.com",
    "wallstreetzen.com",
    "247wallst.com",
    "stockstotrade.com",
    "robinhood.com",
}

_Q_LABEL_RE = re.compile(r"^(\d{4})Q([1-4])$")


def quarter_end_date(q_label):
    m = _Q_LABEL_RE.fullmatch(q_label or "")
    if not m:
        return None
    year, qi = int(m.group(1)), int(m.group(2))
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(year, *ends[qi])


# 季度结束超过这么多天后, 财报必然已发布, F 行不允许继续存在
FORECAST_GRACE_DAYS = 120
# quality_metrics 现金流财年末距今超过这么多天视为陈旧
QUALITY_METRICS_STALE_DAYS = 550

DISALLOWED_NOTE_TERMS = (
    "估算",
    "估 ",
    "反推",
    "推算",
    "季节性",
    "estimate based",
    "estimated",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def domain(url):
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def iter_companies(data):
    for code, company in data.items():
        if code.startswith("_") or not isinstance(company, dict):
            continue
        yield code, company


def audit_companies(label, path):
    data = load_json(path)
    companies = list(iter_companies(data))
    rows = []
    issues = []
    domain_counts = Counter()

    for code, company in companies:
        quarters = company.get("quarters") or []
        if not quarters:
            issues.append({
                "severity": "warn",
                "type": "no_quarters",
                "market": label,
                "code": code,
                "q": "",
                "message": "No quarterly financial data. This is OK for ETF/watch-only names, but it cannot be used in financial ranking.",
            })
            continue

        for q in quarters:
            src = q.get("src")
            source_url = q.get("source_url") or ""
            source_domain = domain(source_url)
            if source_domain:
                domain_counts[source_domain] += 1

            row = {
                "market": label,
                "code": code,
                "q": q.get("q", ""),
                "src": src,
                "rev": q.get("rev"),
                "gm": q.get("gm"),
                "nm": q.get("nm"),
                "source_url": source_url,
                "note": q.get("note", ""),
            }
            rows.append(row)

            if src not in {"A", "F", "NA"}:
                issues.append({
                    "severity": "error",
                    "type": "bad_src",
                    **row,
                    "message": "src must be A, F, or NA.",
                })

            has_financial_values = any(q.get(k) is not None for k in ("rev", "gm", "nm"))
            if has_financial_values and not source_url:
                issues.append({
                    "severity": "error",
                    "type": "missing_source_url",
                    **row,
                    "message": "Financial row has rev/gm/nm but no source_url.",
                })

            # 政策: src=NA 时 rev/gm/nm 必须为 null
            if src == "NA" and has_financial_values:
                issues.append({
                    "severity": "error",
                    "type": "na_row_has_values",
                    **row,
                    "message": "src is NA but rev/gm/nm still carry values; they must be null.",
                })

            # 政策: F 不得用于已发布财报的历史季度
            if src == "F":
                q_end = quarter_end_date(q.get("q"))
                if q_end and date.today() - q_end > timedelta(days=FORECAST_GRACE_DAYS):
                    issues.append({
                        "severity": "error",
                        "type": "forecast_in_past_quarter",
                        **row,
                        "message": (
                            f"Forecast row for {q.get('q')} but that quarter ended {q_end.isoformat()} "
                            f"(> {FORECAST_GRACE_DAYS} days ago); the actual report must be out — replace with A or NA."
                        ),
                    })

            if src == "F":
                if not source_url:
                    issues.append({
                        "severity": "error",
                        "type": "forecast_missing_source",
                        **row,
                        "message": "Forecast row has no source_url.",
                    })
                note = (q.get("note") or "").lower()
                if not any(word in note for word in ("guidance", "outlook", "consensus", "指引", "一致预期", "管理层")):
                    issues.append({
                        "severity": "error",
                        "type": "forecast_unclear_basis",
                        **row,
                        "message": "Forecast row does not clearly say guidance/outlook/consensus.",
                    })

            if source_domain in DISALLOWED_SOURCE_DOMAINS:
                issues.append({
                    "severity": "error",
                    "type": "disallowed_source_domain",
                    **row,
                    "message": f"{source_domain} is not allowed as a final financial source.",
                })

            note_lower = (q.get("note") or "").lower()
            if has_financial_values and any(term in note_lower for term in DISALLOWED_NOTE_TERMS):
                issues.append({
                    "severity": "error",
                    "type": "estimated_financial_value",
                    **row,
                    "message": "Financial value appears to be estimated/inferred in note.",
                })

        # quality_metrics 审计: 时效 + FCF 算术一致性 (此前 FY2023 陈旧数据正是从这里漏过去的)
        qm = company.get("quality_metrics")
        if isinstance(qm, dict) and not qm.get("manual_override"):
            qm_row = {"market": label, "code": code, "q": "quality_metrics", "src": "", "source_url": qm.get("source_url", "")}
            period = qm.get("operating_cash_flow_period") or ""
            period_end = None
            m = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", period)
            if m:
                try:
                    period_end = date.fromisoformat(m.group(1))
                except ValueError:
                    period_end = None
            if qm.get("operating_cash_flow_billion") is not None:
                if period_end is None:
                    issues.append({
                        "severity": "warn",
                        "type": "quality_metrics_no_period",
                        **qm_row,
                        "message": "quality_metrics has OCF but no parseable operating_cash_flow_period; cannot verify vintage.",
                    })
                elif date.today() - period_end > timedelta(days=QUALITY_METRICS_STALE_DAYS):
                    # warn 而非 error: 20-F 外国公司年报进 SEC XBRL 本身有滞后 (如 TSM), 不是合规违规
                    issues.append({
                        "severity": "warn",
                        "type": "quality_metrics_stale",
                        **qm_row,
                        "message": f"quality_metrics cash flow fiscal year ends {period_end.isoformat()} — stale; re-run fill_us_cash_flow_from_sec.py.",
                    })
            ocf, capex, fcf = qm.get("operating_cash_flow_billion"), qm.get("capex_billion"), qm.get("free_cash_flow_billion")
            if all(isinstance(v, (int, float)) for v in (ocf, capex, fcf)) and abs((ocf - abs(capex)) - fcf) > 0.01:
                issues.append({
                    "severity": "error",
                    "type": "quality_metrics_fcf_mismatch",
                    **qm_row,
                    "message": f"free_cash_flow_billion ({fcf}) != OCF ({ocf}) - CapEx ({capex}).",
                })
            debt_end, cash_end = qm.get("long_term_debt_end"), qm.get("cash_end")
            if debt_end and cash_end and debt_end < cash_end:
                try:
                    gap = date.fromisoformat(cash_end) - date.fromisoformat(debt_end)
                    if gap > timedelta(days=450):
                        issues.append({
                            "severity": "error",
                            "type": "quality_metrics_debt_stale",
                            **qm_row,
                            "message": f"debt balance ({debt_end}) is >15 months older than cash balance ({cash_end}).",
                        })
                except ValueError:
                    pass

        outlook = company.get("q2_outlook")
        if isinstance(outlook, dict):
            source_url = outlook.get("source_url") or ""
            source_domain = domain(source_url)
            profitability = outlook.get("profitability_guidance")
            annual_guidance = outlook.get("annual_guidance")
            has_profitability_guidance = (
                isinstance(profitability, dict)
                and any(profitability.get(k) is not None for k in ("value", "margin_pct"))
            )
            has_outlook_values = (
                any(outlook.get(k) is not None for k in ("rev_estimate", "gm_estimate", "nm_estimate", "yoy_pct"))
                or has_profitability_guidance
            )
            row = {
                "market": label,
                "code": code,
                "q": outlook.get("q", "q2_outlook"),
                "src": "F",
                "rev": outlook.get("rev_estimate"),
                "gm": outlook.get("gm_estimate"),
                "nm": outlook.get("nm_estimate"),
                "source_url": source_url,
                "note": outlook.get("source", "") or outlook.get("catalyst", ""),
                "profitability_guidance": profitability if isinstance(profitability, dict) else None,
            }
            if source_domain:
                domain_counts[source_domain] += 1
            if has_outlook_values and not source_url:
                issues.append({
                    "severity": "error",
                    "type": "outlook_missing_source_url",
                    **row,
                    "message": "q2_outlook has financial estimates but no source_url.",
                })
            if source_domain in DISALLOWED_SOURCE_DOMAINS:
                issues.append({
                    "severity": "error",
                    "type": "outlook_disallowed_source_domain",
                    **row,
                    "message": f"{source_domain} is not allowed as a final outlook source.",
                })
            text = f"{outlook.get('source','')} {outlook.get('catalyst','')}".lower()
            if has_outlook_values and any(term in text for term in DISALLOWED_NOTE_TERMS):
                issues.append({
                    "severity": "error",
                    "type": "outlook_estimated_value",
                    **row,
                    "message": "q2_outlook appears to include inferred/estimated values.",
                })
            if isinstance(annual_guidance, dict) and annual_guidance.get("summary"):
                annual_url = annual_guidance.get("source_url") or ""
                annual_domain = domain(annual_url)
                if annual_domain:
                    domain_counts[annual_domain] += 1
                if not annual_url:
                    issues.append({
                        "severity": "error",
                        "type": "annual_guidance_missing_source_url",
                        **row,
                        "source_url": annual_url,
                        "note": annual_guidance.get("summary", ""),
                        "message": "annual_guidance has a summary but no source_url.",
                    })
                if annual_domain in DISALLOWED_SOURCE_DOMAINS:
                    issues.append({
                        "severity": "error",
                        "type": "annual_guidance_disallowed_source_domain",
                        **row,
                        "source_url": annual_url,
                        "note": annual_guidance.get("summary", ""),
                        "message": f"{annual_domain} is not allowed as a final annual guidance source.",
                    })

    return {
        "market": label,
        "path": str(path.relative_to(ROOT)),
        "companies": len(companies),
        "quarter_rows": len(rows),
        "issues": issues,
        "domain_counts": domain_counts,
    }


def audit_kline_state(label, path):
    if not path.exists():
        return {
            "market": label,
            "path": str(path.relative_to(ROOT)),
            "exists": False,
            "issues": [{
                "severity": "error",
                "type": "missing_kline_state",
                "market": label,
                "message": "K-line scan state file is missing.",
            }],
        }

    data = load_json(path)
    status = data.get("kline_status", "")
    source = data.get("data_source", "")
    failed = []
    if "failed:" in status:
        failed = [x.strip() for x in status.split("failed:", 1)[1].split(",") if x.strip()]

    issues = []
    if "ok" not in status:
        issues.append({
            "severity": "warn",
            "type": "kline_not_ok",
            "market": label,
            "message": f"K-line status is not ok in the saved scan state: {status}. Re-run the scan with network access before relying on fresh trend signals.",
        })
    for code in failed:
        issues.append({
            "severity": "error",
            "type": "kline_failed_symbol",
            "market": label,
            "code": code,
            "message": f"Latest saved K-line scan failed for {code}.",
        })
    if "Tencent" not in source:
        issues.append({
            "severity": "warn",
            "type": "unknown_kline_source",
            "market": label,
            "message": f"Unexpected K-line data source: {source}",
        })

    return {
        "market": label,
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "status": status,
        "source": source,
        "failed": failed,
        "issues": issues,
    }


def main():
    company_audits = [audit_companies(label, path) for label, path in COMPANY_FILES]
    kline_audits = [audit_kline_state(label, path) for label, path in STATE_FILES]

    all_issues = []
    for audit in company_audits:
        all_issues.extend(audit["issues"])
    for audit in kline_audits:
        all_issues.extend(audit["issues"])

    by_type = Counter(issue["type"] for issue in all_issues)
    by_severity = Counter(issue["severity"] for issue in all_issues)

    print("DATA QUALITY AUDIT")
    print("==================")
    for audit in company_audits:
        print(f"{audit['market']}: {audit['companies']} companies, {audit['quarter_rows']} quarter rows, {len(audit['issues'])} issues")
    for audit in kline_audits:
        print(f"{audit['market']} K-line: {audit.get('status', 'missing')} ({len(audit['issues'])} issues)")
    print()
    print("Issues by severity:", dict(by_severity))
    print("Issues by type:", dict(by_type))

    out_path = ROOT / "data_quality_audit.json"
    out = {
        "company_audits": company_audits,
        "kline_audits": kline_audits,
        "issue_counts": {
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
        },
        "issues": all_issues,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.relative_to(ROOT)}")

    return 1 if by_severity.get("error", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
