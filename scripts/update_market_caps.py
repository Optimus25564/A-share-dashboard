#!/usr/bin/env python3
"""Update market_cap_billion for both markets from Futunn REST snapshots.

Futunn total_market_val uses the market currency unit. Divide by 1e8 to match the
dashboard's historical market_cap_billion field (亿元 / 亿美元).
ETF 跳过 (不参与量化)。运行日期写入 _meta.market_cap_updated 和每家公司的
market_cap_asof。
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = json.loads((ROOT / "data" / "futu_snapshot.json").read_text(encoding="utf-8"))["quotes"]


def update_file(path, market):
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = []
    for code, c in data.items():
        if code.startswith("_") or not isinstance(c, dict):
            continue
        if c.get("cat") == "etf":
            continue
        codes.append(code)
    today = date.today().isoformat()
    updated, skipped = 0, []
    for code in codes:
        mc = float(SNAPSHOT.get(code, {}).get("total_market_val") or 0) / 1e8
        c = data[code]
        if not mc or mc <= 0:
            skipped.append(code)
            continue
        old = c.get("market_cap_billion")
        c["market_cap_billion"] = round(mc, 1)
        c["market_cap_asof"] = today
        if old and abs(mc - old) / old > 0.25:
            print(f"  ⚠ {code}: 市值变动 >25% ({old} → {mc:.0f}) — 请人工复核是否有拆股/增发")
        updated += 1
    meta = data.setdefault("_meta", {})
    meta["market_cap_updated"] = (
        f"总市值更新于 {today} · 来源: 富途 OpenAPI REST (A股亿元 / 美股亿美元) · scripts/update_market_caps.py"
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: 更新 {updated} 家" + (f", 无行情跳过: {skipped}" if skipped else ""))


if __name__ == "__main__":
    update_file(ROOT / "data" / "companies.json", "a")
    update_file(ROOT / "data" / "companies_us.json", "us")
