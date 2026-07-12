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
# 每日扫描只在有触发时推送; 手动/push 触发的 workflow 设 FORCE_SEND=1 强制发送完整报告
FORCE_SEND = os.environ.get("FORCE_SEND", "") == "1"

STATES = [
    ("A 股", "data/alerts_state.json", "上证"),
    ("美股", "data/alerts_state_us.json", "QQQ"),
]

BUY_LABEL = {
    "buy-deep": "🎯 深回踩 EMA21 黄金坑",
    "buy":      "🔴 标准回踩 EMA8",
    "buy-fresh": "🔴 回踩 EMA8 转强",  # run_monitor / 旧版扫描产生的买点别名
    "buy-near": "🟡 距 EMA8 ≤3% 接近回踩",
}
SELL_LABEL = {
    "sell-confirmed": "🟢 周线已确认破位 — 清仓",
    "sell-warning":   "⚠ 本周盘中跌破 EMA8 — 等周收盘确认",
}
# 宏观门控后的买点: 展示但不算 actionable, 不触发 🚨
GATED_LABEL = {
    "buy-gated": "🟡 买点出现但大盘走弱 — 仅观察不建仓",
}
KNOWN_NON_ACTION = {"hold", "hold-trend", "no-data", None}


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

    # Normalize (合并两版兼容逻辑): 旧版 A 股 signals 是 dict {"signal": ..., "close_est": ...},
    # 新版 scan_signals.py 是纯字符串。dict 信号里的估算价用作 prices 兜底显示。
    sig_prices = {}
    normalized_signals = {}
    for code, sig in signals.items():
        if isinstance(sig, dict):
            sig_prices[code] = {
                "close": sig.get("close_est", "--"),
                "ema8":  sig.get("ema8_est",  "--"),
                "vs_ema8_pct": sig.get("vs_ema8_pct"),
            }
            normalized_signals[code] = sig.get("signal") or sig.get("action") or "hold"
        else:
            normalized_signals[code] = sig if isinstance(sig, str) else "hold"
    # Merge sig_prices with prices (prices wins for existing keys)
    for code, pdata in sig_prices.items():
        if code not in prices:
            prices[code] = pdata

    # Also absorb US ema_notes if present
    for code, en in (state.get("ema_notes") or {}).items():
        if code not in prices:
            prices[code] = {
                "close": en.get("close"),
                "ema8":  en.get("ema8_est", "--"),
            }

    buckets = {k: [] for k in list(BUY_LABEL) + list(SELL_LABEL) + list(GATED_LABEL)}
    for code, sig in normalized_signals.items():
        if sig in buckets:
            buckets[sig].append(code)
        elif sig not in KNOWN_NON_ACTION:
            print(f"  ⚠ 未识别的信号被忽略: {code} -> {sig!r}", file=sys.stderr)

    actionable = any(buckets[k] for k in list(BUY_LABEL) + list(SELL_LABEL))

    lines = [f"\n## 🏛 {market_label}"]

    # 本次触发 (每日扫描与上一次状态的差异, 由 scan_signals.compute_changes 生成)
    changes = state.get("changes") or []
    if changes:
        lines.append("\n### 🔔 本次触发（为什么现在提醒你）")
        for ch in changes:
            lines.append(f"- {ch}")
    # 大盘 (旧版状态里 market 可能是字符串, 只认 dict)
    mkt = state.get("market")
    if not isinstance(mkt, dict):
        mkt = {}
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
        # 宏观层: 距 52 周高点回撤 + 观察列表空头宽度 (由 scan_signals.py 写入)
        dd = mkt.get("drawdown_from_52w_high_pct")
        if isinstance(dd, (int, float)):
            dd_tag = "🔴 熊市级回撤" if dd <= -20 else ("⚠ 回调区" if dd <= -10 else "")
            lines.append(f"- {index_label} 距 52 周高点: {dd:+.1f}% {dd_tag}".rstrip())
        breadth = mkt.get("breadth_bearish_pct")
        if isinstance(breadth, (int, float)):
            b_tag = "🔴 全面走弱" if breadth >= 60 else ("⚠ 局部走弱" if breadth >= 40 else "")
            lines.append(f"- 观察列表空头宽度: {breadth:.0f}% 处于 sell 信号 {b_tag}".rstrip())
        if mkt.get("buy_gate_active"):
            lines.append(f"- 🚧 宏观门控生效: {mkt.get('buy_gate_reason', '大盘走弱')} — 本期买点全部降级为观察")
        # 宏观仓位阶梯建议 (由 scan_signals.py 按 大盘EMA8/EMA21/52周回撤/宽度 生成)
        if mkt.get("position_advice"):
            lines.append(f"- **仓位建议**: {mkt['position_advice']}")

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
    for k in ["buy-deep", "buy", "buy-fresh", "buy-near"]:
        codes = buckets[k]
        if codes:
            lines.append(f"\n### {BUY_LABEL[k]}")
            for code in codes:
                nm = name_map.get(code, code)
                p = prices.get(code, {})
                close = p.get("close", "--"); pct = p.get("vs_ema8_pct")
                pct_str = f" 距 EMA8 {pct:+.1f}%" if isinstance(pct, (int, float)) else ""
                lines.append(f"- **{nm}** ({code}) close={close}{pct_str}")

    # Gated buys (宏观门控 — 只展示, 不算 actionable)
    for k, label in GATED_LABEL.items():
        codes = buckets.get(k) or []
        if codes:
            lines.append(f"\n### {label}")
            for code in codes:
                nm = name_map.get(code, code)
                p = prices.get(code, {})
                close = p.get("close", "--"); pct = p.get("vs_ema8_pct")
                pct_str = f" 距 EMA8 {pct:+.1f}%" if isinstance(pct, (int, float)) else ""
                lines.append(f"- {nm} ({code}) close={close}{pct_str}")

    if not actionable:
        lines.append("\n✓ 当前无买卖信号（所有持仓 hold / 趋势中）")

    return "\n".join(lines), actionable


run_date = datetime.now().strftime("%Y-%m-%d")
sections = []
any_action = False
any_changes = False
for label, path, idx_label in STATES:
    state = load_state(path)
    if state and state.get("changes"):
        any_changes = True
    section, actionable = section_for(label, state, idx_label)
    if section:
        sections.append(section)
        if actionable:
            any_action = True

if not sections:
    print("No state files found — skipping")
    sys.exit(0)

# 每日扫描的静默规则: 与上一次状态相比没有任何触发 → 不打扰
if not any_changes and not FORCE_SEND:
    print("无新触发 (signals/门控/仓位建议/Top5 均与上次一致) — 跳过推送")
    sys.exit(0)

title = f"🚨 {run_date} 触发调仓提醒" if any_action else f"✅ {run_date} 状态更新"
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
