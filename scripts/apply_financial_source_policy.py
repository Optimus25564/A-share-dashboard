#!/usr/bin/env python3
"""Remove non-compliant financial values from model fields.

Rows without an approved source are not deleted, but their numeric financial
fields are set to null so they cannot affect rankings or Top 5 selection.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data_quality_audit.json"

# quarters 行与 q2_outlook 的 issue 分开建 key —— 同一公司可能同时有
# quarters "2026Q2" 行和 q2_outlook.q == "2026Q2", 混用一个 key 会互相误伤
QUARTER_ISSUE_TYPES = {
    "missing_source_url",
    "disallowed_source_domain",
    "forecast_missing_source",
    "forecast_unclear_basis",
    "estimated_financial_value",
    "forecast_in_past_quarter",
    "na_row_has_values",
}
OUTLOOK_ISSUE_TYPES = {
    "outlook_missing_source_url",
    "outlook_disallowed_source_domain",
    "outlook_estimated_value",
}

FILES = {
    "A-share": ROOT / "data" / "companies.json",
    "US": ROOT / "data" / "companies_us.json",
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    # 审计结果必须比数据文件新, 否则会按过期结论误删已修好的行
    audit_mtime = AUDIT_PATH.stat().st_mtime
    for market, path in FILES.items():
        if path.stat().st_mtime > audit_mtime:
            raise SystemExit(
                f"{path.name} 比 data_quality_audit.json 新 — "
                "先运行 python3 scripts/audit_data_quality.py 刷新审计结果再执行本脚本。"
            )

    audit = load_json(AUDIT_PATH)
    targets_quarters = {}
    targets_outlook = {}
    for issue in audit.get("issues", []):
        key = (issue.get("market"), issue.get("code"), issue.get("q"))
        if issue.get("type") in QUARTER_ISSUE_TYPES:
            targets_quarters[key] = issue
        elif issue.get("type") in OUTLOOK_ISSUE_TYPES:
            targets_outlook[key] = issue

    changed = 0
    for market, path in FILES.items():
        data = load_json(path)
        for code, company in data.items():
            if code.startswith("_") or not isinstance(company, dict):
                continue
            for row in company.get("quarters") or []:
                key = (market, code, row.get("q"))
                issue = targets_quarters.get(key)
                if not issue:
                    continue

                had_values = any(row.get(field) is not None for field in ("rev", "gm", "nm"))
                row["rev"] = None
                row["gm"] = None
                row["nm"] = None
                row["src"] = "NA"
                row["source_url"] = ""
                row["note"] = (
                    "未找到符合规范的真实公告/guidance/consensus 来源；"
                    f"原财务数值已移除，不参与模型。原因：{issue.get('type')}"
                )
                if had_values:
                    changed += 1

            outlook = company.get("q2_outlook")
            key = (market, code, outlook.get("q")) if isinstance(outlook, dict) else None
            issue = targets_outlook.get(key)
            if isinstance(outlook, dict) and issue:
                profitability = outlook.get("profitability_guidance")
                had_values = (
                    any(outlook.get(field) is not None for field in ("rev_estimate", "gm_estimate", "nm_estimate", "yoy_pct"))
                    or (
                        isinstance(profitability, dict)
                        and any(profitability.get(field) is not None for field in ("value", "margin_pct"))
                    )
                )
                outlook["rev_estimate"] = None
                outlook["yoy_pct"] = None
                outlook["gm_estimate"] = None
                outlook["nm_estimate"] = None
                outlook.pop("profitability_guidance", None)
                outlook["source_url"] = ""
                outlook["source"] = "未找到符合规范的真实公告/guidance/consensus 来源"
                outlook["catalyst"] = (
                    "未找到符合规范的真实公告/guidance/consensus 来源；"
                    f"原 outlook 数值已移除。原因：{issue.get('type')}"
                )
                outlook["data_type"] = "NA"
                outlook["confidence"] = "low"
                if had_values:
                    changed += 1
        write_json(path, data)

    print(f"Removed non-compliant financial values from {changed} rows.")


if __name__ == "__main__":
    main()
