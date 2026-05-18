#!/usr/bin/env python3
"""Read both alerts_state.json (A-share) and alerts_state_us.json (US),
push merged notification via WeChat + Gmail.

Signals understood (matches front-end evalWeeklyEMA):
  buy-deep / buy / buy-near       — buy signals (deep > std > near)
  hold-trend / hold               — no action
  sell-warning / sell-confirmed   — sell signals (warning intra-week, confirmed close)
"""
import os
import json
import sys
import urllib.request
import urllib.parse
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS = os.environ.get("GMAIL_PASS", "").replace(" ", "")

STATES = [
    ("A 股", "data/alerts_state.json", "上证"),
    ("美股", "data/alerts_state_us.json", "QQQ"),
]

BUY_LABEL = {
    "buy-deep": "🎯 深回踩 EMA21 黄金坑",
    "buy":      "🔴 标准回踩 EMA8",
    "buy-near": "🟡 距 EMA8 ≤3% 接近回踩",
}
SELL_LABEL = {
    "sell-confirmed": "🟢 周线已确认破位 — 清仓",
    "sell-warning":   "⚠ 本周盘中跌破 EMA8 — 等周收盘确认",
}


def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def section_for(market_label, state, index_label):
    if not state:
        return None, False
    signals = state.get("signals", {})
    prices = state.get("prices", {})
    top5 = state.get("top5", [])
    name_map = {p["code"] if isinstance(p, dict) else p: prices[p]["name"] if isinstance(prices.get(p), dict) and "name" in prices[p] else p
                for p in signals.keys()}
    # fallback: top5 names + prices names
    for t in top5:
        name_map[t["code"]] = t.get("name", t["code"])
    for code, pdata in prices.items():
        if isinstance(pdata, dict) and pdata.get("name"):
            name_map[code] = pdata["name"]

    buckets = {k: [] for k in list(BUY_LABEL) + list(SELL_LABEL)}
    for code, sig in signals.items():
        if sig in buckets:
            buckets[sig].append(code)

    actionable = any(buckets[k] for k in buckets)

    lines = [f"\n## 🏛 {market_label}"]
    # 大盘
    mkt = state.get("market") or {}
    if mkt:
        pct = mkt.get("vs_ema8_pct")
        bull = mkt.get("bullish")
        if pct is None:
            lines.append(f"- {index_label}: 数据未知")
        elif bull:
            tag = "✓ 多头" if pct >= 3 else "⚠ 接近破位"
            lines.append(f"- {index_label}: close={mkt.get('close','--')} EMA8={mkt.get('ema8','--')} 距 EMA8 {pct:+.1f}% {tag}")
        else:
            lines.append(f"- {index_label}: close={mkt.get('close','--')} EMA8={mkt.get('ema8','--')} 距 EMA8 {pct:+.1f}% ✗ 跌破")

    # Top 5
    if top5:
        lines.append("- Top 5: " + " / ".join(t.get("name", t["code"]) for t in top5))

    # Sell groups (first — most urgent)
    for k in ["sell-confirmed", "sell-warning"]:
        codes = buckets[k]
        if codes:
            lines.append(f"\n### {SELL_LABEL[k]}")
            for code in codes:
                nm = name_map.get(code, code)
                p = prices.get(code, {})
                close = p.get("close", "--"); ema8 = p.get("ema8", "--"); pct = p.get("vs_ema8_pct")
                pct_str = f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
                date = p.get("close_date", "")
                base = f"- **{nm}** ({code}) {date} close={close} EMA8={ema8}{pct_str}"
                cur = p.get("current_close")
                cur_date = p.get("current_date")
                if cur is not None and cur_date and cur_date != date:
                    base += f" — 现价 {cur} ({cur_date})"
                lines.append(base)

    # Buy groups
    for k in ["buy-deep", "buy", "buy-near"]:
        codes = buckets[k]
        if codes:
            lines.append(f"\n### {BUY_LABEL[k]}")
            for code in codes:
                nm = name_map.get(code, code)
                p = prices.get(code, {})
                close = p.get("close", "--"); pct = p.get("vs_ema8_pct")
                pct_str = f" 距 EMA8 {pct:+.1f}%" if isinstance(pct, (int, float)) else ""
                lines.append(f"- **{nm}** ({code}) close={close}{pct_str}")

    if not actionable:
        lines.append("\n✓ 当前无买卖信号（所有持仓 hold / 趋势中）")

    return "\n".join(lines), actionable


run_date = datetime.now().strftime("%Y-%m-%d")
sections = []
any_action = False
for label, path, idx_label in STATES:
    state = load_state(path)
    section, actionable = section_for(label, state, idx_label)
    if section:
        sections.append(section)
        if actionable:
            any_action = True

if not sections:
    print("No state files found — skipping")
    sys.exit(0)

title = f"🚨 {run_date} 趋势提醒" if any_action else f"✅ {run_date} 持仓平稳"
body = "## 📊 当前状态 (" + run_date + ")\n" + "\n".join(sections) + "\n\n[查看详情](https://optimus25564.github.io/A-share-dashboard/)"

print(f"Title: {title}")
print(f"Body length: {len(body)}\n")


def push_wechat(title: str, body: str):
    if not SERVERCHAN_KEY:
        return False, "SERVERCHAN_KEY missing"
    try:
        data = urllib.parse.urlencode({"title": title[:32], "desp": body}).encode()
        req = urllib.request.Request(f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
                                     data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            return j.get("code") == 0, f"code={j.get('code')}"
    except Exception as e:
        return False, repr(e)


def push_email(title: str, body: str):
    if not GMAIL_USER or not GMAIL_PASS:
        return False, "Gmail creds missing"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = formataddr(("RMB Invest Dashboard", GMAIL_USER))
        msg["To"] = GMAIL_USER
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(GMAIL_USER, GMAIL_PASS)
            smtp.send_message(msg)
        return True, "ok"
    except Exception as e:
        return False, repr(e)


print("📱 微信...")
ok_wx, msg_wx = push_wechat(title, body)
print(f"   {'✅' if ok_wx else '❌'} {msg_wx}")

print("📧 邮件...")
ok_em, msg_em = push_email(title, body)
print(f"   {'✅' if ok_em else '❌'} {msg_em}")

if not ok_wx and not ok_em:
    sys.exit(1)
