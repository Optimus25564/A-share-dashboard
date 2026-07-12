#!/usr/bin/env python3
"""Update market_cap_billion for both markets from Tencent quotes.

腾讯行情第 45 字段 = 总市值 (A股: 亿元, 美股: 亿美元), 与页面/模型使用的
market_cap_billion 单位一致 (名字里的 billion 是历史遗留, 实际是亿)。
ETF 跳过 (不参与量化)。运行日期写入 _meta.market_cap_updated 和每家公司的
market_cap_asof。
"""
import json
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

US_TICKER_ALIAS = {"ASE": "ASX"}


def fetch_quotes(keys):
    out = {}
    for i in range(0, len(keys), 30):
        batch = keys[i:i + 30]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("gbk", errors="replace")
        for line in raw.split(";"):
            line = line.strip()
            if "=" not in line or "~" not in line:
                continue
            key = line.split("=", 1)[0].replace("v_", "")
            parts = line.split("~")
            if len(parts) > 45:
                try:
                    out[key] = float(parts[45])
                except ValueError:
                    pass
    return out


def update_file(path, market):
    data = json.loads(path.read_text(encoding="utf-8"))
    keymap = {}
    for code, c in data.items():
        if code.startswith("_") or not isinstance(c, dict):
            continue
        if c.get("cat") == "etf":
            continue
        if market == "a":
            keymap[("sh" if code[0] in "69" else "sz") + code] = code
        else:
            keymap["us" + US_TICKER_ALIAS.get(code, code)] = code
    quotes = fetch_quotes(list(keymap))
    today = date.today().isoformat()
    updated, skipped = 0, []
    for key, code in keymap.items():
        mc = quotes.get(key)
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
        f"总市值更新于 {today} · 来源: 腾讯行情 f45 (A股亿元 / 美股亿美元) · scripts/update_market_caps.py"
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: 更新 {updated} 家" + (f", 无行情跳过: {skipped}" if skipped else ""))


if __name__ == "__main__":
    update_file(ROOT / "data" / "companies.json", "a")
    update_file(ROOT / "data" / "companies_us.json", "us")
