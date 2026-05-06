#!/usr/bin/env python3
"""Read data/alerts_state.json and push notifications via WeChat + Gmail.

Triggered by GitHub Actions on push to alerts_state.json. Runs on
GitHub-hosted runner with full internet egress (unlike Anthropic CCR
sandbox which is restricted).
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

STATE_PATH = "data/alerts_state.json"

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS = os.environ.get("GMAIL_PASS", "").replace(" ", "")

if not os.path.exists(STATE_PATH):
    print("alerts_state.json missing — nothing to send")
    sys.exit(0)

with open(STATE_PATH, encoding="utf-8") as f:
    state = json.load(f)

run_date = state.get("run_date", datetime.now().strftime("%Y-%m-%d"))
top5 = state.get("top5", [])
candidates = state.get("candidates", [])
signals = state.get("signals", {})
kline_status = state.get("kline_status", "")

# 判断有无 actionable signals
sells = [(c, sig) for c, sig in signals.items() if sig in ("sell-warning", "sell-confirmed")]
buys = [(c, sig) for c, sig in signals.items() if sig == "buy-fresh"]
has_signal = len(sells) > 0 or len(buys) > 0

# 名字 lookup
name_map = {s["code"]: s["name"] for s in top5 + candidates}
name_map["sh000001"] = "上证指数"

if has_signal:
    title = f"🚨 {run_date} 趋势提醒"
else:
    title = f"✅ {run_date} 持仓平稳"

# Markdown body
body_lines = [f"## 📊 当前状态 ({run_date})"]
body_lines.append("- Top 5: " + " / ".join(s["name"] for s in top5))
if "sh000001" in signals:
    sig = signals["sh000001"]
    if sig == "kline_unavailable":
        body_lines.append(f"- 大盘上证: ⚠ K 线数据获取失败")
    else:
        body_lines.append(f"- 大盘上证: {sig}")
body_lines.append("")

if sells:
    body_lines.append("## 🔴 卖出信号")
    for code, sig in sells:
        nm = name_map.get(code, code)
        body_lines.append(f"- **{nm}** ({code}): {sig}")
    body_lines.append("")

if buys:
    body_lines.append("## 🟢 候选池新买点")
    for code, sig in buys:
        nm = name_map.get(code, code)
        body_lines.append(f"- **{nm}** ({code}): {sig}")
    body_lines.append("")

if not has_signal:
    body_lines.append("## ⚪ 持仓状态")
    for s in top5:
        sig = signals.get(s["code"], "?")
        body_lines.append(f"- {s['name']} {sig}")
    body_lines.append("")

if kline_status and "failed" in kline_status:
    body_lines.append(f"⚠ 注意: {kline_status}")
    body_lines.append("")

body_lines.append(f"[查看详情](https://optimus25564.github.io/A-share-dashboard/)")

body = "\n".join(body_lines)

print(f"Title: {title}")
print(f"Body length: {len(body)}")
print()


def push_wechat(title: str, body: str) -> tuple[bool, str]:
    if not SERVERCHAN_KEY:
        return False, "SERVERCHAN_KEY missing"
    try:
        data = urllib.parse.urlencode({"title": title[:32], "desp": body}).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read().decode())
            ok = j.get("code") == 0
            return ok, f"code={j.get('code')} pushid={j.get('data', {}).get('pushid')}"
    except Exception as e:
        return False, repr(e)


def push_email(title: str, body: str) -> tuple[bool, str]:
    if not GMAIL_USER or not GMAIL_PASS:
        return False, "Gmail creds missing"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = formataddr(("A-share Dashboard", GMAIL_USER))
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
