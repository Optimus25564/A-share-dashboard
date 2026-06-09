#!/usr/bin/env python3
"""Remove non-compliant financial values from model fields.

Rows without an approved source are not deleted, but their numeric financial
fields are set to null so they cannot affect rankings or Top 5 selection.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data_quality_audit.json"

ISSUE_TYPES_TO_REMOVE = {
    "missing_source_url",
    "disallowed_source_domain",
    "forecast_missing_source",
    "forecast_unclear_basis",
    "estimated_financial_value",
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
    audit = load_json(AUDIT_PATH)
    targets = {}
    for issue in audit.get("issues", []):
        if issue.get("type") not in ISSUE_TYPES_TO_REMOVE:
            continue
        key = (issue.get("market"), issue.get("code"), issue.get("q"))
        targets[key] = issue

    changed = 0
    for market, path in FILES.items():
        data = load_json(path)
        for code, company in data.items():
            if code.startswith("_") or not isinstance(company, dict):
                continue
            for row in company.get("quarters") or []:
                key = (market, code, row.get("q"))
                issue = targets.get(key)
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
            issue = targets.get(key)
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
