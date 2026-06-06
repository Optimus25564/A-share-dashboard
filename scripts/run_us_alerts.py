#!/usr/bin/env python3
"""US stock weekly trend monitoring agent."""
import json, math, statistics, urllib.request, csv, io, time
from datetime import datetime, date, timezone, timedelta

BASE = "/home/user/A-share-dashboard"

with open(f"{BASE}/data/companies_us.json") as f:
    companies = json.load(f)

WATCHLIST = ['NVDA','AVGO','AMD','INTC','QCOM','MRVL','APP','TSM','ASML',
             'AMAT','KLAC','ONTO','SNPS','MU','SNDK','COHR','LITE','FN',
             'MSFT','GOOGL','AMZN','META','AAPL','TSLA','CRWV','CEG','VRT',
             'ETN','GEV','CCJ','SMH','XLU','COPX','XME','EWY','RKLB']
ETF_LIST = {'SMH','XLU','COPX','XME','EWY'}

today = date(2026, 6, 6)
is_friday = today.weekday() == 4  # True → sell-confirmed

# ── Step 1: Score calculation ──────────────────────────────────────────────

def get_valid_quarters(d):
    return [q for q in d.get('quarters', []) if q.get('rev') is not None]

def calc_yoy(d):
    qs = get_valid_quarters(d)
    if len(qs) < 2:
        return None
    latest = qs[-1]['rev']
    ref = qs[-5]['rev'] if len(qs) >= 5 else qs[0]['rev']
    if not ref:
        return None
    return max(-50, min(300, (latest / ref - 1) * 100))

def calc_profit(d):
    qs = get_valid_quarters(d)
    if not qs:
        return None, None
    recent = qs[-4:] if len(qs) >= 4 else qs
    gms = [q['gm'] for q in recent if q.get('gm') is not None]
    nms = [q['nm'] for q in recent if q.get('nm') is not None]
    gm = sum(gms)/len(gms) if gms else None
    nm = max(-30, min(60, sum(nms)/len(nms))) if nms else None
    return gm, nm

def z_score_list(pairs):
    """pairs = [(ticker, value), ...]; returns {ticker: z}"""
    if len(pairs) < 2:
        return {t: 0.0 for t, _ in pairs}
    vals = [v for _, v in pairs]
    mu = sum(vals)/len(vals)
    sd = statistics.stdev(vals) or 1.0
    return {t: (v - mu)/sd for t, v in pairs}

raw = {}
for t in WATCHLIST:
    if t not in companies:
        continue
    d = companies[t]
    is_etf = t in ETF_LIST
    yoy = None if is_etf else calc_yoy(d)
    gm, nm = (None, None) if is_etf else calc_profit(d)
    turnover = d.get('avg_turnover_pct', 2)
    mktcap = d.get('market_cap_billion', 100)
    raw[t] = {
        'name': d.get('name', t),
        'is_etf': is_etf,
        'strategic': d.get('strategic', 5),
        'yoy': yoy, 'gm': gm, 'nm': nm,
        'turnover': turnover,
        'liq': -abs(math.log(max(turnover, 0.01) / 5)),
        'log_mc': math.log(max(mktcap, 0.1)),
    }

all_t = list(raw.keys())
non_etf = [t for t in all_t if not raw[t]['is_etf']]

z_strat = z_score_list([(t, raw[t]['strategic']) for t in all_t])
z_liq   = z_score_list([(t, raw[t]['liq']) for t in all_t])
z_mc    = z_score_list([(t, raw[t]['log_mc']) for t in all_t])
z_yoy   = z_score_list([(t, raw[t]['yoy']) for t in non_etf if raw[t]['yoy'] is not None])
z_gm    = z_score_list([(t, raw[t]['gm'])  for t in non_etf if raw[t]['gm']  is not None])
z_nm    = z_score_list([(t, raw[t]['nm'])  for t in non_etf if raw[t]['nm']  is not None])

scores = {}
for t in all_t:
    s = z_strat.get(t, 0)
    l = z_liq.get(t, 0)
    m = z_mc.get(t, 0)
    if raw[t]['is_etf']:
        scores[t] = (40/60)*s + (12/60)*l + (8/60)*m
    else:
        yy = z_yoy.get(t, 0)
        gm = z_gm.get(t, 0)
        nm = z_nm.get(t, 0)
        pr = 0.6*gm + 0.4*nm
        scores[t] = 0.40*s + 0.20*yy + 0.20*pr + 0.12*l + 0.08*m

ranked = sorted(all_t, key=lambda x: scores[x], reverse=True)

# Top 5: non-ETF only
non_etf_ranked = [t for t in ranked if not raw[t]['is_etf']]
top5 = non_etf_ranked[:5]
top5_set = set(top5)

# Candidates: next 5 from overall ranking (can include ETFs)
candidates = [t for t in ranked if t not in top5_set][:5]

print("=== Top 5 ===")
for i, t in enumerate(top5, 1):
    print(f"  {i}. {t} ({raw[t]['name']}) score={scores[t]:.4f}")
print("=== Candidates ===")
for i, t in enumerate(candidates, 1):
    print(f"  {i}. {t} ({raw[t]['name']}) score={scores[t]:.4f}")

# ── Step 2: Fetch Stooq weekly K-lines ─────────────────────────────────────

def fetch_stooq(ticker):
    """Returns list of {date, open, high, low, close, volume}"""
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=w"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for row in reader:
            try:
                rows.append({
                    'date': row['Date'],
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row.get('Volume', 0) or 0)
                })
            except (ValueError, KeyError):
                continue
        return rows[-52:] if rows else []  # last 52 weeks
    except Exception as e:
        print(f"  [WARN] {ticker}: {e}")
        return []

def calc_ema(values, n):
    if not values:
        return []
    k = 2 / (n + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema

def slope5(series):
    """Linear slope of last 5 values, normalized by last value."""
    if len(series) < 5:
        return 0
    y = series[-5:]
    x = list(range(5))
    n = 5
    sx = sum(x); sy = sum(y); sxy = sum(xi*yi for xi,yi in zip(x,y)); sx2 = sum(xi**2 for xi in x)
    denom = n*sx2 - sx*sx
    if denom == 0:
        return 0
    return (n*sxy - sx*sy) / denom / (y[-1] or 1)

def determine_signal(bars, is_friday):
    if len(bars) < 21:
        return 'insufficient-data'
    closes = [b['close'] for b in bars]
    lows   = [b['low']   for b in bars]
    ema8  = calc_ema(closes, 8)
    ema21 = calc_ema(closes, 21)
    last_close = closes[-1]
    last_e8    = ema8[-1]
    last_e21   = ema21[-1]

    if last_close < last_e8:
        return 'sell-confirmed' if is_friday else 'sell-warning'
    elif last_e8 > last_e21 and slope5(ema8) > 0:
        n = len(bars)
        for i in [n-2, n-1]:
            if lows[i] <= ema8[i] * 1.02:
                return 'buy-fresh'
        return 'hold'
    else:
        return 'hold'

# Fetch K-lines for top5 + candidates + market indices
fetch_list = top5 + candidates
market_tickers = ['SPY', 'QQQ']  # market proxies

print("\n=== Fetching K-lines ===")
klines = {}
failed = []
for t in fetch_list:
    print(f"  Fetching {t}...", end=' ')
    bars = fetch_stooq(t)
    if bars:
        klines[t] = bars
        print(f"OK ({len(bars)} weeks)")
    else:
        failed.append(t)
        print("FAILED")
    time.sleep(0.3)

market_klines = {}
for t in market_tickers:
    print(f"  Fetching market {t}...", end=' ')
    bars = fetch_stooq(t)
    if bars:
        market_klines[t] = bars
        print(f"OK ({len(bars)} weeks)")
    else:
        print("FAILED")
    time.sleep(0.3)

# ── Step 3: Determine signals ───────────────────────────────────────────────
print("\n=== Signals ===")
signals = {}
for t in fetch_list:
    bars = klines.get(t, [])
    sig = determine_signal(bars, is_friday)
    signals[t] = sig
    close = bars[-1]['close'] if bars else 'N/A'
    print(f"  {t}: {sig} (last close={close})")

# Market context
market_signal = {}
for t in market_tickers:
    bars = market_klines.get(t, [])
    if bars:
        closes = [b['close'] for b in bars]
        ema8 = calc_ema(closes, 8)
        ema21 = calc_ema(closes, 21)
        trend = 'up' if ema8[-1] > ema21[-1] else 'down'
        market_signal[t] = {
            'close': round(bars[-1]['close'], 2),
            'ema8': round(ema8[-1], 2),
            'ema21': round(ema21[-1], 2),
            'trend': trend
        }

# ── Step 4: Write state file ────────────────────────────────────────────────
now_beijing = datetime.now(timezone(timedelta(hours=8)))
run_date = today.isoformat()

top5_out = [
    {'code': t, 'name': raw[t]['name'], 'rank': i+1, 'score': round(scores[t], 4)}
    for i, t in enumerate(top5)
]
candidates_out = [
    {'code': t, 'name': raw[t]['name'], 'rank': i+6, 'score': round(scores[t], 4)}
    for i, t in enumerate(candidates)
]

kline_ok = len(klines)
kline_total = len(fetch_list)
kline_status = "ok" if not failed else f"partial: {kline_ok}/{kline_total} ok; failed={','.join(failed)}"

output = {
    "last_run": now_beijing.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
    "run_date": run_date,
    "market": "US",
    "is_friday": is_friday,
    "market_context": market_signal,
    "top5": top5_out,
    "candidates": candidates_out,
    "signals": signals,
    "kline_status": kline_status,
    "sources": "stooq weekly K-line",
    "score_details": {
        t: {
            'score': round(scores[t], 4),
            'strategic': raw[t]['strategic'],
            'yoy_pct': round(raw[t]['yoy'], 1) if raw[t]['yoy'] is not None else None,
            'avg_gm': round(raw[t]['gm'], 1) if raw[t]['gm'] is not None else None,
            'avg_nm_clipped': round(raw[t]['nm'], 1) if raw[t]['nm'] is not None else None,
        }
        for t in WATCHLIST if t in raw
    }
}

out_path = f"{BASE}/data/alerts_state_us.json"
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n=== Written to {out_path} ===")
print(json.dumps({
    'top5': [f"{x['rank']}.{x['code']}" for x in top5_out],
    'candidates': [f"{x['rank']}.{x['code']}" for x in candidates_out],
    'signals': signals,
    'kline_status': kline_status,
    'market': market_signal
}, ensure_ascii=False, indent=2))
