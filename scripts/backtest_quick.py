#!/usr/bin/env python3
"""Quick backtest for the dashboard Top 5 + weekly EMA8 exit rule.

This is intentionally a fast sanity check, not a full historical fundamental
backtest. It uses today's company data and quant ranking for the whole period,
so the ranking has look-ahead bias. The thing it tests is the trend-exit /
replacement rule:

  hold current quant Top 5 -> if weekly close < weekly EMA8, replace from the
  next-ranked eligible names -> rebalance only when a replacement is needed.
"""
import argparse
import csv
import json
import math
import sys
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

US_EXCHANGE = {
    "TSM": "N", "ONTO": "N", "FN": "N", "VRT": "N", "ETN": "N",
    "GEV": "N", "CCJ": "N", "COHR": "N", "ANET": "N", "CIEN": "N",
    "GLW": "N", "PWR": "N", "EME": "N", "FIX": "N", "MOD": "N",
    "TT": "N", "JCI": "N", "HUBB": "N", "VST": "N", "NRG": "N",
    "KMI": "N", "WMB": "N", "ORCL": "N", "NOW": "N", "CRM": "N",
    "ASE": "N",
    "EWY": "P",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pfx_a(code):
    return ("sh" if code.startswith("6") else "sz") + code


def sym_us(ticker):
    return f"us{ticker}.{US_EXCHANGE.get(ticker, 'OQ')}"


def fetch_weekly_bars(symbol, market, count):
    if market == "a":
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},week,,,{count},qfq"
    else:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param={symbol},week,,,{count},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    node = data.get("data", {}).get(symbol, {})
    rows = node.get("week") or node.get("qfqweek") or []
    out = []
    for row in rows:
        try:
            out.append({
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5]),
            })
        except (IndexError, TypeError, ValueError):
            continue
    return out


def ema(values, n):
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def zscore(values):
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    sd = math.sqrt(var) or 1
    return [(v - mean) / sd for v in values]


def derive_watchlist(companies):
    return [
        code for code, c in companies.items()
        if not code.startswith("_") and c.get("name") and c.get("cat") != "etf"
    ]


def compute_quant_weights(companies, codes):
    valid = []
    for code in codes:
        c = companies.get(code) or {}
        qs = c.get("quarters") or []
        if len(qs) < 5:
            continue
        if not all(q.get("rev") is not None and q.get("gm") is not None and q.get("nm") is not None for q in qs):
            continue
        rev_base = qs[0]["rev"]
        rev_yoy = (qs[-1]["rev"] / rev_base - 1) * 100 if rev_base > 0 else 0
        t = c.get("avg_turnover_pct") or 3
        valid.append({
            "code": code,
            "logMC": math.log(c.get("market_cap_billion") or 100),
            "revYoY": max(-50, min(300, rev_yoy)),
            "gm": qs[-1]["gm"],
            "nm": qs[-1]["nm"],
            "nmClipped": max(-30, min(60, qs[-1]["nm"])),
            "turnoverScore": -abs(math.log(t / 5)),
            "strategic": (c.get("strategic") or 5) / 10,
        })
    if len(valid) < 5:
        raise RuntimeError("not enough companies with complete factor data")

    z_mc = zscore([r["logMC"] for r in valid])
    z_growth = zscore([r["revYoY"] for r in valid])
    z_gm = zscore([r["gm"] for r in valid])
    z_nm = zscore([r["nmClipped"] for r in valid])
    z_to = zscore([r["turnoverScore"] for r in valid])
    z_profit = [0.6 * z_gm[i] + 0.4 * z_nm[i] for i in range(len(valid))]
    w = {"mc": 0.08, "growth": 0.20, "profit": 0.20, "turnover": 0.12, "strategic": 0.40}

    composites = []
    for i, r in enumerate(valid):
        score = (
            w["mc"] * z_mc[i]
            + w["growth"] * z_growth[i]
            + w["profit"] * z_profit[i]
            + w["turnover"] * z_to[i]
            + w["strategic"] * r["strategic"] * 2
        )
        composites.append(score)

    min_score = min(composites)
    shifted = [score - min_score + 0.5 for score in composites]
    total = sum(shifted)
    weights = [round(x / total * 100, 1) for x in shifted]
    drift = round(100 - sum(weights), 1)
    if abs(drift) > 0:
        weights[weights.index(max(weights))] = round(max(weights) + drift, 1)

    ranked = []
    for i, r in enumerate(valid):
        ranked.append({"code": r["code"], "score": composites[i], "weight": weights[i]})
    ranked.sort(key=lambda x: -x["weight"])
    return ranked


def prep_bars(raw_bars):
    closes = [b["close"] for b in raw_bars]
    e8 = ema(closes, 8)
    out = {}
    for i, b in enumerate(raw_bars):
        item = dict(b)
        item["ema8"] = e8[i]
        out[b["date"]] = item
    return out


def active_top5(ranked, bars_by_code, dt):
    active = []
    for r in ranked:
        b = bars_by_code.get(r["code"], {}).get(dt)
        if not b:
            continue
        if b["close"] < b["ema8"]:
            continue
        active.append(r)
        if len(active) == 5:
            break
    return active


def target_weights(holdings):
    total = sum(h["weight"] for h in holdings)
    return {h["code"]: h["weight"] / total for h in holdings}


def portfolio_value(shares, bars_by_code, dt):
    total = 0
    for code, qty in shares.items():
        b = bars_by_code.get(code, {}).get(dt)
        if not b:
            return None
        total += qty * b["close"]
    return total


def rebalance(value, holdings, bars_by_code, dt):
    weights = target_weights(holdings)
    shares = {}
    for code, weight in weights.items():
        price = bars_by_code[code][dt]["close"]
        shares[code] = value * weight / price
    return shares


def max_drawdown(equity):
    peak = equity[0][1]
    worst = 0
    for _, value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return worst


def annualized_return(equity):
    start = date.fromisoformat(equity[0][0])
    end = date.fromisoformat(equity[-1][0])
    years = max((end - start).days / 365.25, 1 / 365.25)
    total = equity[-1][1] / equity[0][1] - 1
    return (1 + total) ** (1 / years) - 1


def run_backtest(args):
    companies = load_json(DATA_DIR / ("companies.json" if args.market == "a" else "companies_us.json"))
    names = {code: c.get("name", code) for code, c in companies.items() if isinstance(c, dict)}
    watch = derive_watchlist(companies)
    ranked = compute_quant_weights(companies, watch)
    pool = ranked[:args.pool_size]

    print(f"Market: {'A 股' if args.market == 'a' else '美股'}")
    print(f"Pool size: {len(pool)} from current quant ranking")
    print("Top ranked:", " / ".join(f"{r['code']}({r['weight']:.1f})" for r in pool[:10]))
    print("Fetching weekly K-lines...")

    bars_by_code = {}
    failed = []
    for r in pool:
        code = r["code"]
        symbol = pfx_a(code) if args.market == "a" else sym_us(code)
        try:
            bars = fetch_weekly_bars(symbol, args.market, args.count)
            if len(bars) < 30:
                raise RuntimeError(f"only {len(bars)} bars")
            bars_by_code[code] = prep_bars(bars)
        except Exception as exc:
            failed.append((code, str(exc)))
    if failed:
        print("Skipped fetch failures:", ", ".join(f"{c} ({e})" for c, e in failed), file=sys.stderr)
    if not bars_by_code:
        raise RuntimeError("no K-line data fetched; check network/DNS access to Tencent quote endpoints")

    ranked = [r for r in pool if r["code"] in bars_by_code]
    all_dates = sorted({dt for bars in bars_by_code.values() for dt in bars})
    dates = [dt for dt in all_dates if dt >= args.start]
    if not dates:
        raise RuntimeError("no dates in requested backtest window")

    first_dt = None
    current = None
    for dt in dates:
        current = active_top5(ranked, bars_by_code, dt)
        if len(current) == 5:
            first_dt = dt
            break
    if not first_dt:
        raise RuntimeError("could not form an initial active Top 5")

    shares = rebalance(args.cash, current, bars_by_code, first_dt)
    equity = [(first_dt, args.cash)]
    trades = [{
        "date": first_dt,
        "action": "initial",
        "holdings": [h["code"] for h in current],
        "sold": [],
        "bought": [h["code"] for h in current],
        "value": args.cash,
    }]

    for dt in dates[dates.index(first_dt) + 1:]:
        value = portfolio_value(shares, bars_by_code, dt)
        if value is None:
            continue
        held = set(shares)
        broken = {
            code for code in held
            if bars_by_code[code][dt]["close"] < bars_by_code[code][dt]["ema8"]
        }
        if broken:
            next_holdings = active_top5(ranked, bars_by_code, dt)
            if len(next_holdings) == 5:
                next_codes = {h["code"] for h in next_holdings}
                shares = rebalance(value, next_holdings, bars_by_code, dt)
                trades.append({
                    "date": dt,
                    "action": "rebalance",
                    "holdings": [h["code"] for h in next_holdings],
                    "sold": sorted(held - next_codes),
                    "bought": sorted(next_codes - held),
                    "value": value,
                })
        equity.append((dt, value))

    total_return = equity[-1][1] / equity[0][1] - 1
    print("\n=== Result ===")
    print(f"Period: {equity[0][0]} -> {equity[-1][0]} ({len(equity)} weekly points)")
    print(f"Final value: {equity[-1][1]:,.0f}")
    print(f"Total return: {total_return:+.2%}")
    print(f"Annualized: {annualized_return(equity):+.2%}")
    print(f"Max drawdown: {max_drawdown(equity):.2%}")
    print(f"Rebalances: {max(0, len(trades) - 1)}")
    if args.equity_csv:
        out_path = Path(args.equity_csv)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "equity", "return_pct", "drawdown_pct"])
            peak = equity[0][1]
            start_value = equity[0][1]
            for dt, value in equity:
                peak = max(peak, value)
                writer.writerow([
                    dt,
                    f"{value:.2f}",
                    f"{(value / start_value - 1) * 100:.4f}",
                    f"{(value / peak - 1) * 100:.4f}",
                ])
        print(f"Equity curve CSV: {out_path}")

    print("\n=== Trades ===")
    for t in trades[: args.max_trades]:
        label = "INITIAL" if t["action"] == "initial" else "REBAL"
        print(f"{t['date']} {label} value={t['value']:,.0f}")
        if t["sold"]:
            print("  sell:", " / ".join(f"{c} {names.get(c, c)}" for c in t["sold"]))
        if t["bought"]:
            print("  buy :", " / ".join(f"{c} {names.get(c, c)}" for c in t["bought"]))
        print("  hold:", " / ".join(f"{c} {names.get(c, c)}" for c in t["holdings"]))
    if len(trades) > args.max_trades:
        print(f"... {len(trades) - args.max_trades} more trades omitted")

    print("\nNote: quick backtest uses current factor ranking for the whole history; this has look-ahead bias.")


def main():
    parser = argparse.ArgumentParser(description="Quick Top 5 + weekly EMA8 exit backtest")
    parser.add_argument("--market", choices=["a", "us"], default="a", help="market to test")
    parser.add_argument("--start", default="2024-01-01", help="start date YYYY-MM-DD")
    parser.add_argument("--cash", type=float, default=1_000_000, help="initial capital")
    parser.add_argument("--pool-size", type=int, default=15, help="ranked candidates to fetch")
    parser.add_argument("--count", type=int, default=320, help="weekly bars to request per symbol")
    parser.add_argument("--max-trades", type=int, default=80, help="max trade rows to print")
    parser.add_argument("--equity-csv", help="optional CSV path for weekly equity curve")
    args = parser.parse_args()
    run_backtest(args)


if __name__ == "__main__":
    main()
