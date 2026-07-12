import json, math, os, statistics, urllib.request, urllib.parse, smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Load data ────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
with open(BASE / 'data' / 'companies.json') as f:
    companies = json.load(f)

CODES_17 = ['688256','688041','002261','300308','002837','603019',
            '000977','000034','000938','002156','688008','688981',
            '300475','002409','688347','688047','601138']

def get_latest_val(qs, field):
    for q in reversed(qs):
        v = q.get(field)
        if v is not None: return v
    return None

def safe_yoy(q3, q0):
    if q3 is None or q0 is None or q0 == 0: return None
    return max(-0.5, min(3.0, q3/q0 - 1))

def zscore_list(pairs):
    valid = [(k,v) for k,v in pairs if v is not None]
    if len(valid) < 2: return {k:0 for k,v in pairs}
    mu = statistics.mean(v for _,v in valid)
    sd = statistics.stdev(v for _,v in valid)
    return {k: ((v-mu)/sd if sd else 0) if v is not None else 0 for k,v in pairs}

# ─── Build records ────────────────────────────────────────────
records = {}
for code in CODES_17:
    c = companies.get(code, {})
    qs = c.get('quarters', [])
    # 真 YoY: 最新季 vs 4 季前同期 (quarters 升序, ≥5 季才可比)
    yoy_base = qs[-5].get('rev') if len(qs) >= 5 else None
    yoy_last = qs[-1].get('rev') if len(qs) >= 5 else None
    nm_raw = get_latest_val(qs, 'nm')
    records[code] = {
        'name': c.get('name', '?'),
        'strategic': c.get('strategic', 5),
        'yoy': safe_yoy(yoy_last, yoy_base),
        'gm': get_latest_val(qs, 'gm'),
        'nm_clipped': max(-30, min(60, nm_raw)) if nm_raw is not None else None,
        'turnover': c.get('avg_turnover_pct', 5),
        'mcap': c.get('market_cap_billion', 1000),
    }

# ─── Z-scores & scoring ───────────────────────────────────────
z_strat = zscore_list([(c, records[c]['strategic']) for c in CODES_17])
z_yoy   = zscore_list([(c, records[c]['yoy']) for c in CODES_17])
z_gm    = zscore_list([(c, records[c]['gm']) for c in CODES_17])
z_nm    = zscore_list([(c, records[c]['nm_clipped']) for c in CODES_17])
z_liq   = zscore_list([(c, -abs(math.log(max(records[c]['turnover'], 0.01)/5))) for c in CODES_17])
z_mcap  = zscore_list([(c, math.log(records[c]['mcap'])) for c in CODES_17])

scores = {}
for code in CODES_17:
    scores[code] = (0.40*z_strat[code] + 0.20*z_yoy[code] +
                    0.20*(0.6*z_gm[code]+0.4*z_nm[code]) +
                    0.12*z_liq[code] + 0.08*z_mcap[code])

ranked = sorted(CODES_17, key=lambda c: scores[c], reverse=True)

print("=== RANKING ===")
for i, code in enumerate(ranked):
    r = records[code]
    yoy_str = f"{r['yoy']:.1%}" if r['yoy'] is not None else "N/A"
    print(f"  #{i+1} {code} {r['name']}: score={scores[code]:.3f} strat={r['strategic']} yoy={yoy_str} gm={r['gm']} nm={r['nm_clipped']}")

top5  = ranked[:5]
cand5 = ranked[5:10]
watch10 = top5 + cand5
print("\nTop5:", [(c, records[c]['name']) for c in top5])
print("候选:", [(c, records[c]['name']) for c in cand5])

# ─── EMA helpers ──────────────────────────────────────────────
def ema(values, n):
    k = 2/(n+1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v*k + result[-1]*(1-k))
    return result

def slope5(series):
    if len(series) < 5: return 0
    vals = series[-5:]
    return (vals[-1] - vals[0]) / 4

# ─── Fetch weekly K-lines ─────────────────────────────────────
def sym_code(code):
    return ('sh' if code[0] in ('6','9') else 'sz') + code

def fetch_weekly(sym):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},week,,,320,qfq"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        raw = data.get('data', {})
        for key in raw:
            wk = raw[key].get('qfqweek') or raw[key].get('week')
            if wk:
                return wk
    except Exception as e:
        print(f"  fetch error {sym}: {e}")
    return None

bj_now = datetime.now(timezone(timedelta(hours=8)))
today_str = bj_now.strftime('%Y-%m-%d')
weekday = bj_now.weekday()
# 周线 bar 收盘确认: 周五 15:15 后, 或周末 (周内跌破只算 warning, 避免拿未完成的周线确认卖出)
minute_of_day = bj_now.hour * 60 + bj_now.minute
week_bar_closed = (weekday == 4 and minute_of_day >= 15 * 60 + 15) or weekday in (5, 6)
is_friday = week_bar_closed
print(f"\n今日: {today_str} 周{weekday+1} 周线已收盘={week_bar_closed}")

all_codes = watch10 + ['sh000001']
klines = {}
for code in all_codes:
    sym = 'sh000001' if code == 'sh000001' else sym_code(code)
    bars = fetch_weekly(sym)
    if bars:
        closes = [float(b[2]) for b in bars]
        highs  = [float(b[3]) for b in bars]
        lows   = [float(b[4]) for b in bars]
        dates  = [b[0] for b in bars]
        e8  = ema(closes, 8)
        e21 = ema(closes, 21)
        klines[code] = {'dates': dates, 'closes': closes, 'highs': highs,
                        'lows': lows, 'ema8': e8, 'ema21': e21}
        print(f"  {sym}: {len(bars)}bars last={dates[-1]} close={closes[-1]:.2f} ema8={e8[-1]:.2f} ema21={e21[-1]:.2f}")
    else:
        print(f"  {sym}: NO DATA")

# ─── Signal detection ──────────────────────────────────────────
def detect_signal(code):
    if code not in klines:
        return 'no-data', {}
    d = klines[code]
    closes = d['closes']; lows = d['lows']
    e8 = d['ema8']; e21 = d['ema21']
    n = len(closes)
    last_close = closes[-1]; last_e8 = e8[-1]
    if last_close < last_e8:
        sig = 'sell-confirmed' if is_friday else 'sell-warning'
    elif e8[-1] > e21[-1] and slope5(e8) > 0:
        sig = 'hold'
        for i in [n-2, n-1]:
            if lows[i] <= e8[i] * 1.02:
                sig = 'buy-fresh'
                break
    else:
        sig = 'hold'
    pct = (last_close/last_e8 - 1)*100 if last_e8 else 0
    return sig, {'close': last_close, 'ema8': last_e8, 'ema21': e21[-1], 'pct_vs_e8': pct}

signals = {}
print("\n=== SIGNALS ===")
for code in all_codes:
    sig, info = detect_signal(code)
    signals[code] = {'signal': sig, **info}
    nm = records.get(code, {}).get('name', '上证')
    print(f"  {code} {nm}: {sig} close={info.get('close',0):.2f} ema8={info.get('ema8',0):.2f} pct={info.get('pct_vs_e8',0):.1f}%")

# ─── Compose markdown ──────────────────────────────────────────
def nm(c): return records.get(c, {}).get('name', c)

idx = signals.get('sh000001', {})
idx_close = idx.get('close', 0)
idx_e8    = idx.get('ema8', 0)
idx_sig   = idx.get('signal', 'hold')

if 'sell' in idx_sig:
    idx_line = f"⚠ 跌破 EMA8 周线 ({idx_close:.2f} < {idx_e8:.2f})"
    idx_warn = "⚠ **大盘上证跌破 EMA8，注意风险！**\n\n"
else:
    idx_line = f"✓ 站上 EMA8 周线 ({idx_close:.2f} > {idx_e8:.2f})"
    idx_warn = ""

sell_lines = []
hold_lines = []
buy_lines  = []

for i, code in enumerate(top5):
    s = signals.get(code, {})
    sig = s.get('signal', 'no-data')
    cl  = s.get('close', 0)
    e8v = s.get('ema8', 0)
    pct = s.get('pct_vs_e8', 0)
    if 'sell' in sig:
        action = '趋势破位' if sig == 'sell-confirmed' else '周内跌破EMA8（待确认）'
        sell_lines.append(f"- **{nm(code)}** (持仓#{i+1}): 收盘 {cl:.2f} < EMA8 {e8v:.2f} → {action}")
    else:
        hold_lines.append(f"- {nm(code)} hold ({'+' if pct>=0 else ''}{pct:.1f}% vs EMA8 {e8v:.2f})")

index_bearish = 'sell' in idx_sig
for i, code in enumerate(cand5):
    s = signals.get(code, {})
    sig = s.get('signal', 'no-data')
    cl  = s.get('close', 0)
    e8v = s.get('ema8', 0)
    pct = s.get('pct_vs_e8', 0)
    if sig == 'buy-fresh':
        if index_bearish:
            # 宏观门控: 大盘跌破 EMA8 时买点只报观察, 不作为建仓信号
            buy_lines.append(f"- 🟡 {nm(code)} (候选#{i+6}): 回踩 EMA8 ({e8v:.2f}) 后收 {cl:.2f} — 大盘走弱, 仅观察不建仓")
        else:
            buy_lines.append(f"- **{nm(code)}** (候选#{i+6}): 回踩 EMA8 ({e8v:.2f}) 后收 {cl:.2f} → 多头排列上行")

# 大盘走弱时买点不触发 🚨 (只有卖出/破位才算 actionable)
has_signal = bool(sell_lines or (buy_lines and not index_bearish))
title = f"🚨 [{today_str}] 趋势提醒" if has_signal else f"✅ [{today_str}] 持仓平稳"

top5_names = ' / '.join(nm(c) for c in top5)

body = idx_warn
body += f"## 📊 当前状态 ({today_str})\n"
body += f"- Top 5 持仓: {top5_names}\n"
body += f"- 大盘上证: {idx_line}\n"

if sell_lines:
    body += "\n## 🔴 卖出信号\n" + "\n".join(sell_lines) + "\n"

if buy_lines:
    body += "\n## 🟢 候选池新买点\n" + "\n".join(buy_lines) + "\n"

body += "\n## ⚪ 持仓状态\n" + "\n".join(hold_lines) + "\n"

cand_lines = []
for i, code in enumerate(cand5):
    s = signals.get(code, {})
    pct = s.get('pct_vs_e8', 0)
    e8v = s.get('ema8', 0)
    sig = s.get('signal', 'no-data')
    cand_lines.append(f"- {nm(code)} (#{i+6}) {sig} ({'+' if pct>=0 else ''}{pct:.1f}% vs EMA8 {e8v:.2f})")

body += "\n## 候选池状态\n" + "\n".join(cand_lines) + "\n"
body += "\n[查看详情](https://optimus25564.github.io/A-share-dashboard/)\n"

print("\n=== TITLE ===")
print(title)
print("\n=== BODY ===")
print(body)

# ─── Dedup: 只在信号发生变化时推送 ─────────────────────────────
STATE_PATH = BASE / 'data' / 'alerts_state.json'
prev_sig_map = {}
try:
    with open(STATE_PATH, encoding='utf-8') as f:
        prev = json.load(f)
    for row in prev.get('top5', []) + prev.get('candidates', []):
        v = row.get('signal')
        prev_sig_map[row.get('code')] = v.get('signal') if isinstance(v, dict) else v
    pidx = prev.get('index_sh000001', {}).get('signal')
    prev_sig_map['sh000001'] = pidx.get('signal') if isinstance(pidx, dict) else pidx
except Exception:
    pass  # 无历史状态 → 全部视为新信号

cur_sig_map = {c: signals.get(c, {}).get('signal') for c in top5 + cand5 + ['sh000001']}
changed = {c: s for c, s in cur_sig_map.items() if prev_sig_map.get(c) != s}
should_push = has_signal and (not prev_sig_map or bool(changed))
if not should_push:
    print("\n信号与上次推送一致或无 actionable 信号, 跳过推送 (状态照常归档)")

# ─── Send WeChat ──────────────────────────────────────────────
# 凭证一律从环境变量读取, 不得写进代码/仓库
SERVERCHAN_KEY = os.environ.get('SERVERCHAN_KEY', '')
GMAIL_USER = os.environ.get('ALERT_GMAIL_USER', '')
GMAIL_APP_PASSWORD = os.environ.get('ALERT_GMAIL_APP_PASSWORD', '')

if should_push and SERVERCHAN_KEY:
    print("\n--- 微信推送 ---")
    try:
        payload = urllib.parse.urlencode({'title': title[:32], 'desp': body}).encode()
        req = urllib.request.Request(
            f'https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send',
            data=payload, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            b = json.loads(r.read())
            pushid = b.get('data', {}).get('pushid', '?') if isinstance(b.get('data'), dict) else '?'
            print(f"微信: code={b.get('code')} pushid={pushid}")
    except Exception as e:
        print(f"微信失败: {e}")
elif should_push:
    print("\n微信跳过: 未设置 SERVERCHAN_KEY 环境变量")

# ─── Send Email ───────────────────────────────────────────────
if should_push and GMAIL_USER and GMAIL_APP_PASSWORD:
    print("--- 邮件推送 ---")
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = title
        msg['From'] = formataddr(('A-share Dashboard', GMAIL_USER))
        msg['To'] = GMAIL_USER
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print('邮件: ok')
    except Exception as e:
        print(f'邮件失败: {e}')
elif should_push:
    print("邮件跳过: 未设置 ALERT_GMAIL_USER / ALERT_GMAIL_APP_PASSWORD 环境变量")

# ─── Archive state ─────────────────────────────────────────────
state = {
    'date': today_str,
    'top5': [{'code': c, 'name': nm(c), 'signal': signals.get(c, {}).get('signal', '?'),
              'close': signals.get(c, {}).get('close', 0),
              'ema8': signals.get(c, {}).get('ema8', 0)} for c in top5],
    'candidates': [{'code': c, 'name': nm(c), 'signal': signals.get(c, {}).get('signal', '?'),
                    'close': signals.get(c, {}).get('close', 0),
                    'ema8': signals.get(c, {}).get('ema8', 0)} for c in cand5],
    'index_sh000001': {'signal': idx_sig, 'close': idx_close, 'ema8': idx_e8},
    'title': title,
    'has_signal': has_signal,
    'ranked_top10': [{c: nm(c)} for c in ranked[:10]],
}
with open(STATE_PATH, 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print("状态已写入 data/alerts_state.json")
