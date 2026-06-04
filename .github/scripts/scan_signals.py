#!/usr/bin/env python3
"""Fetch real K-line + compute signals + write alerts_state.json{,_us}.

Replaces the WebSearch-based CCR routine which was producing incorrect EMA
values (sandbox can't reach Tencent K-line; routine fabricated EMAs from
news articles). This runs on GitHub Actions with full internet egress.

Mirrors the front-end `evalWeeklyEMA` and `computeQuantWeights*` logic in
index.html exactly.
"""
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")

# ============================================================
# Watchlist 从 data/companies.json 派生 (与 index.html WATCH 共享)
# ============================================================
def derive_watchlist(companies):
    """Filter to entries with name+cat metadata (mirrors index.html buildWatchFromCompanies)."""
    out = []
    for code, c in companies.items():
        if code.startswith("_"):
            continue
        if c.get("cat") == "etf":
            continue
        name = c.get("name")
        cat = c.get("cat")
        if not name or not cat:
            continue
        out.append((code, name, cat, c.get("catLabel", "")))
    return out

# US exchange mapping (mirrors US_EXCHANGE in index.html)
US_EXCHANGE = {
    "TSM": "N", "ONTO": "N", "FN": "N", "VRT": "N", "ETN": "N",
    "GEV": "N", "CCJ": "N", "COHR": "N", "ANET": "N", "CIEN": "N",
    "GLW": "N", "PWR": "N", "EME": "N", "FIX": "N", "MOD": "N",
    "TT": "N", "JCI": "N", "HUBB": "N", "VST": "N", "NRG": "N",
    "KMI": "N", "WMB": "N", "ORCL": "N", "NOW": "N", "CRM": "N",
    "ASE": "N",  # ASE Technology — NYSE
    "EWY": "P",
}


def pfx_a(code: str) -> str:
    return ("sh" if code[0] == "6" else "sz") + code


def sym_us(ticker: str) -> str:
    ex = US_EXCHANGE.get(ticker, "OQ")
    return f"us{ticker}.{ex}"


# ============================================================
# Tencent K-line fetcher (weekly, fq adjusted)
# ============================================================
def fetch_kline(sym: str, period: str = "week", count: int = 60, market: str = "a"):
    """Return list of dicts [{date, open, close, high, low, volume}]."""
    if market == "a":
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},{period},,,{count},qfq"
    else:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param={sym},{period},,,{count},qfq"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read().decode())
        node = j.get("data", {}).get(sym, {})
        arr = node.get(period) or node.get("qfq" + period) or node.get("day") or []
        out = []
        for row in arr:
            try:
                out.append({
                    "date": row[0],
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]),
                })
            except (ValueError, IndexError):
                continue
        return out
    except Exception as e:
        print(f"  fetch_kline({sym}) failed: {e}", file=sys.stderr)
        return []


def ema(values, n):
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


# ============================================================
# Signal engine (mirrors evalWeeklyEMA in index.html)
# ============================================================
def eval_weekly_ema(bars, index_bullish=None):
    n = len(bars)
    if n < 22:
        return None
    closes = [b["close"] for b in bars]
    e8_arr = ema(closes, 8)
    e21_arr = ema(closes, 21)
    last = bars[-1]
    prev = bars[-2]
    e8 = e8_arr[-1]
    e21 = e21_arr[-1]
    e8_prev = e8_arr[-2]

    # 反转检测: 上周破位但本周强势收回 EMA8 → 跳过 sell-confirmed, 继续走 buy 判定
    prev_broke = prev["close"] < e8_prev
    rebound_reclaim = prev_broke and last["close"] >= e8 * 1.005

    # sell-confirmed: 上一根完整周线 close < EMA8 + 本周未强势收回
    if prev_broke and not rebound_reclaim:
        return {
            "action": "sell-confirmed", "strength": 3,
            "detail": f"上一周收盘 {prev['close']:.2f} < EMA8({e8_prev:.2f}) — 趋势已破位",
            "ema8": e8, "ema21": e21,
            "ref_close": prev["close"], "ref_ema8": e8_prev, "ref_date": prev["date"],
        }
    # sell-warning: 本周(未收盘) close < EMA8
    if last["close"] < e8:
        return {
            "action": "sell-warning", "strength": 2,
            "detail": f"本周收盘 {last['close']:.2f} < EMA8({e8:.2f})，但周线未收盘 — 等本周五收盘后确认",
            "ema8": e8, "ema21": e21,
        }

    stacked = e8 > e21
    e8_rising = e8 > e8_arr[-5]
    e21_rising = e21 > e21_arr[-5]
    if not stacked:
        return {
            "action": "hold", "strength": 1,
            "detail": f"EMA8 ({e8:.2f}) ≤ EMA21 ({e21:.2f}) — 尚未多头排列",
            "ema8": e8, "ema21": e21,
        }
    if not e8_rising or not e21_rising:
        return {
            "action": "hold", "strength": 1,
            "detail": f"已多头排列但 5 周斜率未向上 — 趋势未确认",
            "ema8": e8, "ema21": e21,
        }

    # 加分项 (放量 + 大盘)
    vol10 = sum(b["volume"] for b in bars[-11:-1]) / 10 or 1
    vol_ratio = last["volume"] / vol10
    vol_bonus = vol_ratio > 1.0

    reb_pfx = "⚡反转 · " if rebound_reclaim else ""

    # buy-deep: 本周 low ≤ EMA21 × 1.01
    if last["low"] <= e21 * 1.01:
        return {
            "action": "buy-deep", "strength": 3,
            "detail": f"{reb_pfx}深回踩 EMA21 ({e21:.2f}) — 黄金坑",
            "ema8": e8, "ema21": e21, "vol_ratio": vol_ratio, "index_bullish": index_bullish,
            "rebound": rebound_reclaim,
        }
    # buy: 本周 low ≤ EMA8 × 1.005
    if last["low"] <= e8 * 1.005:
        strength = 3 if rebound_reclaim else 2
        if not vol_bonus and index_bullish is False and not rebound_reclaim:
            strength = 1
        return {
            "action": "buy", "strength": strength,
            "detail": f"{reb_pfx}本周{'假破位后强势收回' if rebound_reclaim else '回踩'} EMA8 ({e8:.2f})，现价 {last['close']:.2f}",
            "ema8": e8, "ema21": e21, "vol_ratio": vol_ratio, "index_bullish": index_bullish,
            "rebound": rebound_reclaim,
        }
    # buy-near: 距 EMA8 ≤ 3%
    above_pct = (last["close"] - e8) / e8 * 100
    if above_pct <= 3:
        return {
            "action": "buy-near", "strength": 2 if rebound_reclaim else 1,
            "detail": f"{reb_pfx}距 EMA8 +{above_pct:.1f}% — {'假破位反扑站回' if rebound_reclaim else '接近回踩区'}",
            "ema8": e8, "ema21": e21, "above_ema8_pct": above_pct,
            "rebound": rebound_reclaim,
        }

    return {
        "action": "hold-trend", "strength": 1,
        "detail": f"多头趋势延续，现价高于 EMA8 {above_pct:.1f}% (> 3%)",
        "ema8": e8, "ema21": e21, "above_ema8_pct": above_pct,
    }


# ============================================================
# 5-factor quant model (mirrors computeQuantWeights in index.html)
# ============================================================
def compute_quant(companies, watch_codes):
    """5 因子量化模型. quarters 严格要求 5 季 (Q1 同期 → Q1) → q[-1]/q[0]-1 = 真 YoY."""
    IDEAL_T = 5
    valid = []
    for code in watch_codes:
        c = companies.get(code)
        if not c:
            continue
        qs = c.get("quarters") or []
        if len(qs) < 5:
            continue
        if not all(q.get("rev") is not None and q.get("gm") is not None and q.get("nm") is not None for q in qs):
            continue
        rev_latest = qs[-1]["rev"]      # 2026Q1
        rev_base = qs[0]["rev"]          # 2025Q1 (同期)
        rev_yoy = (rev_latest / rev_base - 1) * 100 if rev_base > 0 else 0  # 真 YoY
        rev_yoy = max(-50, min(300, rev_yoy))
        gm = qs[-1]["gm"]
        nm = qs[-1]["nm"]
        nm_clipped = max(-30, min(60, nm))
        t = c.get("avg_turnover_pct") or 3
        t_score = -abs(math.log(t / IDEAL_T))
        valid.append({
            "code": code,
            "logMC": math.log(c.get("market_cap_billion") or 100),
            "revYoY": rev_yoy,
            "gm": gm, "nm": nm, "nmClipped": nm_clipped,
            "tScore": t_score,
            "strategic": (c.get("strategic") or 5) / 10,
        })
    if len(valid) < 4:
        return []

    def z(vals):
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / len(vals)
        sd = math.sqrt(var) or 1
        return [(v - m) / sd for v in vals]

    zMC = z([r["logMC"] for r in valid])
    zG = z([r["revYoY"] for r in valid])
    zGM = z([r["gm"] for r in valid])
    zNM = z([r["nmClipped"] for r in valid])
    zT = z([r["tScore"] for r in valid])
    zP = [0.6 * zGM[i] + 0.4 * zNM[i] for i in range(len(valid))]

    W = {"mc": 0.08, "growth": 0.20, "profit": 0.20, "turnover": 0.12, "strategic": 0.40}
    scores = []
    for i, r in enumerate(valid):
        s = (W["mc"] * zMC[i] + W["growth"] * zG[i] + W["profit"] * zP[i]
             + W["turnover"] * zT[i] + W["strategic"] * r["strategic"] * 2)
        scores.append({"code": r["code"], "score": round(s, 3)})
    scores.sort(key=lambda x: -x["score"])
    return scores


# ============================================================
# Per-market scan
# ============================================================
def scan_market(market, watchlist, index_sym, companies):
    """market in {'a', 'us'}, watchlist: list of (code, name, cat, catLabel)."""
    label = "A 股" if market == "a" else "美股"
    print(f"\n=== 扫描 {label} ({len(watchlist)} 只) ===")

    # 1) Index (大盘) — 周线 EMA8
    index_bars = fetch_kline(index_sym, "week", 60, market=market)
    index_close = index_ema8 = index_diff_pct = None
    index_bullish = None
    if len(index_bars) >= 9:
        i_e8 = ema([b["close"] for b in index_bars], 8)
        index_close = index_bars[-1]["close"]
        index_ema8 = i_e8[-1]
        index_diff_pct = (index_close - index_ema8) / index_ema8 * 100
        index_bullish = index_close > index_ema8
        print(f"  大盘 {index_sym}: close={index_close:.2f} EMA8={index_ema8:.2f} diff={index_diff_pct:+.2f}% bullish={index_bullish}")
    else:
        print(f"  ⚠ 大盘 {index_sym} K 线获取失败")

    # 2) Per-stock signals
    signals = {}
    prices = {}
    fail = []
    for code, name, *_ in watchlist:
        sym = pfx_a(code) if market == "a" else sym_us(code)
        bars = fetch_kline(sym, "week", 60, market=market)
        if len(bars) < 22:
            fail.append(code)
            continue
        sig = eval_weekly_ema(bars, index_bullish)
        if not sig:
            fail.append(code)
            continue
        signals[code] = sig["action"]
        # 对 sell-confirmed: 显示破位那一周的 close / EMA8（让数字与判定一致）
        if sig["action"] == "sell-confirmed":
            ref_close = sig.get("ref_close", bars[-2]["close"])
            ref_ema8 = sig.get("ref_ema8", sig["ema8"])
            ref_date = sig.get("ref_date", bars[-2]["date"])
            prices[code] = {
                "name": name,
                "close": round(ref_close, 2),
                "close_date": ref_date,
                "ema8": round(ref_ema8, 2),
                "ema21": round(sig["ema21"], 2),
                "vs_ema8_pct": round((ref_close - ref_ema8) / ref_ema8 * 100, 2),
                "current_close": round(bars[-1]["close"], 2),
                "current_date": bars[-1]["date"],
                "action": sig["action"],
                "strength": sig["strength"],
                "detail": sig["detail"],
            }
        else:
            prices[code] = {
                "name": name,
                "close": round(bars[-1]["close"], 2),
                "close_date": bars[-1]["date"],
                "ema8": round(sig["ema8"], 2),
                "ema21": round(sig["ema21"], 2),
                "vs_ema8_pct": round((bars[-1]["close"] - sig["ema8"]) / sig["ema8"] * 100, 2),
                "action": sig["action"],
                "strength": sig["strength"],
                "detail": sig["detail"],
            }
        time.sleep(0.15)  # 不要打太快被限流

    print(f"  完成 {len(signals)}/{len(watchlist)}, 失败 {fail or 'none'}")

    # 3) Quant Top 5
    quant = compute_quant(companies, [w[0] for w in watchlist])
    name_map = {w[0]: w[1] for w in watchlist}
    top5 = [{"code": q["code"], "name": name_map.get(q["code"], q["code"]),
             "rank": i + 1, "score": q["score"]} for i, q in enumerate(quant[:5])]
    candidates = [{"code": q["code"], "name": name_map.get(q["code"], q["code"]),
                   "rank": i + 6, "score": q["score"]} for i, q in enumerate(quant[5:10])]

    # 4) Build state
    now_cn = datetime.now(timezone(timedelta(hours=8)))
    state = {
        "last_run": now_cn.isoformat(timespec="seconds"),
        "run_date": now_cn.strftime("%Y-%m-%d"),
        "top5": top5,
        "candidates": candidates,
        "signals": signals,
        "prices": prices,
        "market": {
            "code": index_sym,
            "close": round(index_close, 2) if index_close else None,
            "ema8": round(index_ema8, 2) if index_ema8 else None,
            "vs_ema8_pct": round(index_diff_pct, 2) if index_diff_pct is not None else None,
            "bullish": index_bullish,
        },
        "kline_status": f"ok ({len(signals)}/{len(watchlist)})" + (f" — failed: {','.join(fail)}" if fail else ""),
        "data_source": "Tencent ifzq.gtimg.cn (live)",
    }
    if index_bullish is not None:
        signals[index_sym] = "hold" if index_bullish else "sell-confirmed"
    return state


def main():
    # A 股
    with open(os.path.join(DATA_DIR, "companies.json"), encoding="utf-8") as f:
        companies_a = json.load(f)
    watch_a = derive_watchlist(companies_a)
    state_a = scan_market("a", watch_a, "sh000001", companies_a)
    with open(os.path.join(DATA_DIR, "alerts_state.json"), "w", encoding="utf-8") as f:
        json.dump(state_a, f, ensure_ascii=False, indent=2)
    print(f"\n写入 alerts_state.json — top5: {[t['name'] for t in state_a['top5']]}")
    actionable_a = [(c, s) for c, s in state_a["signals"].items() if s.startswith(("buy", "sell"))]
    print(f"  actionable: {actionable_a or '无'}")

    # 美股
    with open(os.path.join(DATA_DIR, "companies_us.json"), encoding="utf-8") as f:
        companies_us = json.load(f)
    watch_us = derive_watchlist(companies_us)
    state_us = scan_market("us", watch_us, sym_us("QQQ"), companies_us)
    with open(os.path.join(DATA_DIR, "alerts_state_us.json"), "w", encoding="utf-8") as f:
        json.dump(state_us, f, ensure_ascii=False, indent=2)
    print(f"\n写入 alerts_state_us.json — top5: {[t['name'] for t in state_us['top5']]}")
    actionable_us = [(c, s) for c, s in state_us["signals"].items() if s.startswith(("buy", "sell"))]
    print(f"  actionable: {actionable_us or '无'}")


if __name__ == "__main__":
    main()
