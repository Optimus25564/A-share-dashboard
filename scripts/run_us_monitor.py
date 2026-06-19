#!/usr/bin/env python3
"""US stock weekly EMA8/EMA21 trend monitor."""
import json, math, statistics, datetime, urllib.request, sys, time

DATA_PATH = "/home/user/A-share-dashboard/data/companies_us.json"
OUTPUT_PATH = "/home/user/A-share-dashboard/data/alerts_state_us.json"

TARGET_TICKERS = [
    "NVDA","AVGO","AMD","INTC","QCOM","MRVL","APP","TSM","ASML","AMAT",
    "KLAC","ONTO","SNPS","MU","SNDK","COHR","LITE","FN","MSFT","GOOGL",
    "AMZN","META","AAPL","TSLA","CRWV","CEG","VRT","ETN","GEV","CCJ",
    "SMH","XLU","COPX","XME","EWY","RKLB"
]
ETF_TICKERS = {"SMH","XLU","COPX","XME","EWY"}

def safe_z(values, mean, std):
    if std == 0:
        return 0
    return (values - mean) / std

def compute_scores(data):
    tickers = [t for t in TARGET_TICKERS if t in data]

    # Collect raw factor values
    strategics, revs, gms, nms, turnovers, caps = {}, {}, {}, {}, {}, {}

    for t in tickers:
        c = data[t]
        strategics[t] = c.get("strategic", 5)
        caps[t] = math.log(max(c.get("market_cap_billion", 1), 0.01))
        to = c.get("avg_turnover_pct", 1.0)
        turnovers[t] = -abs(math.log(max(to, 0.01) / 5))

        q = c.get("quarters", [])
        if t in ETF_TICKERS or len(q) < 4:
            revs[t] = None
            gms[t] = None
            nms[t] = None
        else:
            # YoY: quarters[3].rev / quarters[0].rev - 1
            rev_newest = q[-1]["rev"]
            rev_oldest = q[0]["rev"]
            yoy = (rev_newest / rev_oldest - 1) * 100 if rev_oldest > 0 else 0
            yoy = max(-50, min(300, yoy))
            revs[t] = yoy

            avg_gm = statistics.mean([x["gm"] for x in q if x.get("gm") is not None])
            gms[t] = avg_gm

            nm_vals = [max(-30, min(60, x["nm"])) for x in q if x.get("nm") is not None]
            nms[t] = statistics.mean(nm_vals) if nm_vals else None

    # Compute z-scores for non-ETF tickers
    def z_score_dict(d, valid_keys):
        vals = [d[k] for k in valid_keys if d.get(k) is not None]
        if len(vals) < 2:
            return {k: 0 for k in valid_keys}
        mu, sd = statistics.mean(vals), statistics.stdev(vals)
        return {k: (d[k] - mu) / sd if (d.get(k) is not None and sd > 0) else 0 for k in valid_keys}

    non_etf = [t for t in tickers if t not in ETF_TICKERS]
    etf_list = [t for t in tickers if t in ETF_TICKERS]

    z_rev = z_score_dict(revs, non_etf)
    z_gm = z_score_dict(gms, non_etf)
    z_nm = z_score_dict(nms, non_etf)
    z_to = z_score_dict(turnovers, tickers)
    z_cap = z_score_dict(caps, tickers)

    scores = {}
    for t in tickers:
        strat = strategics[t] / 10.0  # normalize to ~0-1
        strat_z = (strat - 0.7) / 0.15  # rough z-score

        if t in ETF_TICKERS:
            # ETF: strategic 40%, cap 8%, liquidity 12% -> renormalize to 3 factors
            # Use relative weights: strat=40, cap=8, liq=12 -> total 60, renorm to 100
            score = (40 * strat_z + 8 * z_cap[t] + 12 * z_to[t]) / 60
        else:
            profit = 0.6 * z_gm.get(t, 0) + 0.4 * z_nm.get(t, 0)
            score = (0.40 * strat_z + 0.20 * z_rev.get(t, 0) +
                     0.20 * profit + 0.12 * z_to[t] + 0.08 * z_cap[t])
        scores[t] = round(score, 4)

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    # Top 5 = non-ETF only, candidates from next 5 non-ETF (ETF can be in extended pool)
    non_etf_ranked = [(t, s) for t, s in ranked if t not in ETF_TICKERS]
    top5 = non_etf_ranked[:5]
    candidates = non_etf_ranked[5:10]

    return scores, top5, candidates

def fetch_weekly_kline(ticker):
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=w"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            return None
        # Parse CSV: Date,Open,High,Low,Close,Volume
        bars = []
        for line in lines[1:]:  # skip header
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                bar = {
                    "date": parts[0],
                    "open": float(parts[1]),
                    "high": float(parts[2]),
                    "low": float(parts[3]),
                    "close": float(parts[4]),
                    "volume": float(parts[5]) if len(parts) > 5 and parts[5] else 0,
                }
                bars.append(bar)
            except ValueError:
                continue
        return bars if len(bars) >= 20 else None
    except Exception as e:
        print(f"  WARN: {ticker} fetch failed: {e}", file=sys.stderr)
        return None

def compute_ema(values, n):
    k = 2.0 / (n + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema

def compute_signal(ticker, bars, run_date):
    closes = [b["close"] for b in bars]
    lows = [b["low"] for b in bars]
    ema8 = compute_ema(closes, 8)
    ema21 = compute_ema(closes, 21)

    last_close = closes[-1]
    last_ema8 = ema8[-1]
    last_ema21 = ema21[-1]

    # Is today Friday?
    is_friday = run_date.weekday() == 4

    if last_close < last_ema8:
        signal = "sell-confirmed" if is_friday else "sell-warning"
    elif ema8[-1] > ema21[-1]:
        # Check 5-week slope
        slope5 = (ema8[-1] - ema8[-6]) / ema8[-6] if len(ema8) >= 6 else 0
        if slope5 > 0:
            signal = "hold"
            n = len(bars)
            for i in [n-2, n-1]:
                if 0 <= i < n and lows[i] <= ema8[i] * 1.02:
                    signal = "buy-fresh"
                    break
        else:
            signal = "hold"
    else:
        signal = "hold"

    return signal, {
        "ema8": round(last_ema8, 2),
        "ema21": round(last_ema21, 2),
        "close": round(last_close, 2),
        "last_date": bars[-1]["date"]
    }

def main():
    run_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    run_date = run_dt.date()

    print(f"Run time: {run_dt.isoformat()}")

    with open(DATA_PATH) as f:
        raw = json.load(f)
    data = {k: v for k, v in raw.items() if k != "_meta"}

    scores, top5, candidates = compute_scores(data)

    print("=== TOP 5 (non-ETF) ===")
    for rank, (t, s) in enumerate(top5, 1):
        print(f"  {rank}. {t} ({data[t]['name']}) score={s}")

    print("=== CANDIDATES (6-10) ===")
    for rank, (t, s) in enumerate(candidates, 6):
        print(f"  {rank}. {t} ({data[t]['name']}) score={s}")

    # Tickers to fetch K-lines: top5 + candidates + benchmark
    watch_tickers = [t for t, _ in top5] + [t for t, _ in candidates]
    bench_tickers = ["SPY", "QQQ"]
    all_fetch = list(dict.fromkeys(watch_tickers + bench_tickers))

    print(f"\nFetching weekly K-lines for: {all_fetch}")

    klines = {}
    signals = {}
    kline_fails = []

    for ticker in all_fetch:
        print(f"  Fetching {ticker}...", end="", flush=True)
        bars = fetch_weekly_kline(ticker)
        if bars:
            klines[ticker] = bars
            sig, meta = compute_signal(ticker, bars, run_date)
            signals[ticker] = sig
            print(f" {len(bars)} bars, close={meta['close']}, EMA8={meta['ema8']}, EMA21={meta['ema21']}, signal={sig}")
        else:
            kline_fails.append(ticker)
            signals[ticker] = "no-data"
            print(" FAILED")
        time.sleep(0.5)

    kline_status = "ok" if not kline_fails else f"partial: failed={kline_fails}"

    # Build output
    top5_out = [
        {"code": t, "name": data[t]["name"], "rank": i+1, "score": scores[t], "signal": signals.get(t, "no-data")}
        for i, (t, _) in enumerate(top5)
    ]
    candidates_out = [
        {"code": t, "name": data[t]["name"], "rank": i+6, "score": scores[t], "signal": signals.get(t, "no-data")}
        for i, (t, _) in enumerate(candidates)
    ]

    # Summarize key market info
    bench_info = {}
    for b in bench_tickers:
        if b in klines:
            bars = klines[b]
            closes = [x["close"] for x in bars]
            ema8 = compute_ema(closes, 8)
            ema21 = compute_ema(closes, 21)
            bench_info[b] = {
                "close": round(closes[-1], 2),
                "ema8": round(ema8[-1], 2),
                "ema21": round(ema21[-1], 2),
                "signal": signals.get(b, "no-data"),
                "last_date": bars[-1]["date"]
            }

    # Count signal types
    sig_counts = {}
    for v in signals.values():
        sig_counts[v] = sig_counts.get(v, 0) + 1

    output = {
        "last_run": run_dt.isoformat(),
        "run_date": str(run_date),
        "market": "US",
        "top5": top5_out,
        "candidates": candidates_out,
        "signals": signals,
        "signal_summary": sig_counts,
        "benchmark": bench_info,
        "kline_status": kline_status,
        "sources": "stooq weekly K-line"
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWritten to {OUTPUT_PATH}")
    print(f"Signal summary: {sig_counts}")

    return output

if __name__ == "__main__":
    result = main()
