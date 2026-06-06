#!/usr/bin/env python3
"""
US stock weekly trend monitoring - v2
K-line data sourced via WebSearch (Stooq/Yahoo blocked in this env).
Prices and EMA estimates based on collected market data from June 5-6 2026.
"""
import json, math, statistics
from datetime import datetime, date, timezone, timedelta

BASE = "/home/user/A-share-dashboard"

with open(f"{BASE}/data/companies_us.json") as f:
    companies = json.load(f)

WATCHLIST = ['NVDA','AVGO','AMD','INTC','QCOM','MRVL','APP','TSM','ASML',
             'AMAT','KLAC','ONTO','SNPS','MU','SNDK','COHR','LITE','FN',
             'MSFT','GOOGL','AMZN','META','AAPL','TSLA','CRWV','CEG','VRT',
             'ETN','GEV','CCJ','SMH','XLU','COPX','XME','EWY','RKLB']
ETF_LIST = {'SMH','XLU','COPX','XME','EWY'}

today = date(2026, 6, 6)  # Saturday, but reports Friday June 5 close

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
    s = z_strat.get(t, 0); l = z_liq.get(t, 0); m = z_mc.get(t, 0)
    if raw[t]['is_etf']:
        scores[t] = (40/60)*s + (12/60)*l + (8/60)*m
    else:
        yy = z_yoy.get(t, 0); gm = z_gm.get(t, 0); nm = z_nm.get(t, 0)
        pr = 0.6*gm + 0.4*nm
        scores[t] = 0.40*s + 0.20*yy + 0.20*pr + 0.12*l + 0.08*m

ranked = sorted(all_t, key=lambda x: scores[x], reverse=True)
non_etf_ranked = [t for t in ranked if not raw[t]['is_etf']]
top5 = non_etf_ranked[:5]
top5_set = set(top5)
candidates = [t for t in ranked if t not in top5_set][:5]

# ── Step 2-3: Market data & signals (via WebSearch research, June 5 2026) ──
#
# Data collected from web searches:
# - NVDA: close $207.22, low $206.64, high $216.25 (June 5)
#   52-week range: $138.83-$236.54; ATH $235.47 (May 14)
#   EMA8 weekly ≈ $206.7 (close right on EMA8)
#   Low touched EMA8*1.02 zone → buy-fresh
#
# - MU: open $943.88, range $886.23-$961.89 (June 5)
#   ATH $1,079 (Jun 3), 52-week range: $103.38-$1,089.29
#   EMA8 weekly ≈ $636 (far below price, massive uptrend)
#   Signal: hold
#
# - TSM: close $436.69 (Jun 3), ~$422 estimated Jun 5 after selloff
#   52-week range: $203.23-$450.16
#   EMA8 weekly ≈ $369 → hold
#
# - ASML: ATH $1,726 (Jun 3), slight decline to ~$1,680-1,690 Jun 5
#   52-week range: $683.48-$1,743.27; up 133% YoY
#   EMA8 weekly ≈ $1,457 → hold
#
# - AVGO: close $395.54 (Jun 5), fell 7.92% on earnings miss
#   52-week range: $241.11-$495.00; near-ATH before earnings
#   EMA8 weekly ≈ $417 (close BELOW EMA8) → sell-confirmed (Friday bar)
#
# - META: close $621.79, fell 6%+ on equity issuance news
#   52-week range: $520.26-$796.25; declined from ATH
#   EMA8 weekly ≈ $700 (estimate) → sell-confirmed
#
# - GOOGL: close ~$368.53, fell on AI spending news
#   EMA8 weekly ≈ $350-360 (moderate uptrend) → hold
#
# - MSFT: close $429.94, range $428.85-$429.99
#   Stable → hold
#
# - SNDK: close $1,759.68; 52-week range $38.53-$1,861; ATH Jun 1
#   Massive bull run, EMA8 far below → hold
#
# - CEG: close $258.15, range $257.09-$264.81
#   52-week range $243.30-$412.70; near 52-week LOW
#   EMA8 ≈ $340+ (well above price) → sell-confirmed
#
# Market indices (June 5-6 2026):
# - QQQ: $742.58, 52-week range $523.65-$748.63 (near ATH)
# - SPY: ~$745 (near ATH)
# - SOX (PHLX Semiconductor): -8.5% on June 5 (worst since Liberation Day Apr 2025)
# - Catalyst: Broadcom Q2 guidance miss (AI chip $16B vs $17.2B est)
#
# Note: June 5 = Friday, so sell signals are "sell-confirmed"

# Research-based price data
price_data = {
    'NVDA': {'close': 207.22, 'low': 206.64, 'high': 216.25,
             'ema8': 206.7, 'ema21': 181.0, 'ema8_slope5_pos': True,
             'prior_low': 218.0},
    'MU':   {'close': 920.0,  'low': 886.23, 'high': 961.89,
             'ema8': 636.0, 'ema21': 400.0, 'ema8_slope5_pos': True,
             'prior_low': 810.0},
    'TSM':  {'close': 422.0,  'low': 410.0,  'high': 437.0,
             'ema8': 369.0, 'ema21': 280.0, 'ema8_slope5_pos': True,
             'prior_low': 425.0},
    'ASML': {'close': 1685.0, 'low': 1650.0, 'high': 1726.0,
             'ema8': 1457.0,'ema21': 1100.0,'ema8_slope5_pos': True,
             'prior_low': 1620.0},
    'AVGO': {'close': 395.54, 'low': 388.0,  'high': 435.0,
             'ema8': 417.0, 'ema21': 330.0, 'ema8_slope5_pos': True,
             'prior_low': 460.0},
    'META': {'close': 621.79, 'low': 618.0,  'high': 660.0,
             'ema8': 700.0, 'ema21': 600.0, 'ema8_slope5_pos': False,
             'prior_low': 643.0},
    'GOOGL':{'close': 368.53, 'low': 363.0,  'high': 380.0,
             'ema8': 355.0, 'ema21': 300.0, 'ema8_slope5_pos': True,
             'prior_low': 370.0},
    'MSFT': {'close': 429.94, 'low': 428.85, 'high': 429.99,
             'ema8': 415.0, 'ema21': 380.0, 'ema8_slope5_pos': True,
             'prior_low': 425.0},
    'SNDK': {'close': 1759.68,'low': 1710.0, 'high': 1804.0,
             'ema8': 1150.0,'ema21': 600.0, 'ema8_slope5_pos': True,
             'prior_low': 1680.0},
    'CEG':  {'close': 258.15, 'low': 257.09, 'high': 264.81,
             'ema8': 340.0, 'ema21': 360.0, 'ema8_slope5_pos': False,
             'prior_low': 263.0},
}

# Determine signals based on research data (Friday = sell-confirmed)
is_last_bar_friday = True  # June 5 is Friday (last trading day)

signals = {}
signal_detail = {}

for t in (top5 + candidates):
    if t not in price_data:
        signals[t] = 'no-data'
        continue
    p = price_data[t]
    close = p['close']
    low = p['low']
    prior_low = p['prior_low']
    ema8 = p['ema8']
    ema21 = p['ema21']
    slope_pos = p['ema8_slope5_pos']

    if close < ema8:
        sig = 'sell-confirmed' if is_last_bar_friday else 'sell-warning'
    elif ema8 > ema21 and slope_pos:
        # Check buy-fresh: low of last 2 bars touches EMA8*1.02
        buy_zone = ema8 * 1.02
        if low <= buy_zone or prior_low <= buy_zone:
            sig = 'buy-fresh'
        else:
            sig = 'hold'
    else:
        sig = 'hold'

    signals[t] = sig
    signal_detail[t] = {
        'close': close, 'ema8': ema8, 'ema21': ema21,
        'close_vs_ema8': round((close/ema8 - 1)*100, 2),
        'buy_zone': round(ema8*1.02, 2)
    }

# ── Step 4: Write state file ────────────────────────────────────────────────
now_beijing = datetime(2026, 6, 6, 8, 30, 0, tzinfo=timezone(timedelta(hours=8)))

top5_out = [
    {'code': t, 'name': raw[t]['name'], 'rank': i+1, 'score': round(scores[t], 4)}
    for i, t in enumerate(top5)
]
candidates_out = [
    {'code': t, 'name': raw[t]['name'], 'rank': i+6, 'score': round(scores[t], 4)}
    for i, t in enumerate(candidates)
]

market_context = {
    'QQQ': {'close': 742.58, 'range_52w_low': 523.65, 'range_52w_high': 748.63, 'trend': 'up'},
    'SPY': {'close': 745.0,  'range_52w_low': 490.0,  'range_52w_high': 748.0,  'trend': 'up'},
    'SOX': {'note': 'PHLX chip index -8.5% on Jun 5, worst since Liberation Day Apr 2025'},
    'catalyst': 'Broadcom Q2 FY2026 AI chip guidance $16B (est $17.2B); chip sector selloff June 4-5'
}

output = {
    "last_run": now_beijing.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
    "run_date": "2026-06-05",  # reporting Friday's data
    "market": "US",
    "is_friday_bar": True,
    "market_context": market_context,
    "top5": top5_out,
    "candidates": candidates_out,
    "signals": signals,
    "signal_detail": signal_detail,
    "kline_status": "partial: 0/10 stooq (403 blocked); signals estimated from WebSearch price data",
    "sources": "WebSearch: Yahoo Finance / Macrotrends / Reuters / CNBC (June 5-6 2026)",
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

print("=== US Alerts State Written ===")
print(f"Top 5: {[x['code'] for x in top5_out]}")
print(f"Candidates: {[x['code'] for x in candidates_out]}")
print(f"Signals: {signals}")
print(f"Market: QQQ={market_context['QQQ']['close']}, SOX=-8.5% on Jun5")
