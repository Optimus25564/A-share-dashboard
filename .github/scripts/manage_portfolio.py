#!/usr/bin/env python3
"""自动策略盘: 按既定量化规则每日检查、事件驱动换仓, 并把原因写进推送。

规则 (与页面策略说明一致):
  持仓层  - 个股周线收盘跌破 EMA21 (核心趋势破坏) → 卖出, 由排名内合格者顶补
          - 持仓掉出量化 Top10 (排名缓冲: 掉出 Top5 不动, 掉出 Top10 才换) → 换入更高排名者
          - EMA8 破位只观察, 不交易
  宏观层  - 大盘跌破周线 EMA21 或观察列表宽度 ≥60% (buy_gate) → 卫星舱 20% 转现金
          - 指数距 52 周高点 ≤ -20% → 核心舱减半 (40%), 当日立即执行 (熊市保护不等周五)
          - 门控解除 → 按排名买回卫星舱
  纪律    - 除 -20% 保护外, 交易只在周线收盘确认后执行 (周五收盘后的运行)
          - 无触发则不动 (不做定期再平衡)

数据依赖: data/alerts_state{,_us}.json (当日扫描) + data/model_scores.json (6因子排名)。
账本: data/portfolio_a.json / data/portfolio_us.json (由本脚本独家管理)。
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_signals import is_last_weekly_bar_closed  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = lambda *p: os.path.join(ROOT, "data", *p)

CONFIG = {
    "a": dict(state=D("alerts_state.json"), book=D("portfolio_a.json"),
              initial=3_000_000, lot=100, cur="¥", label="A股"),
    "us": dict(state=D("alerts_state_us.json"), book=D("portfolio_us.json"),
               initial=300_000, lot=1, cur="$", label="美股"),
}
TOP_CORE, TOP_ALL, RANK_EXIT = 5, 10, 10  # 核心5 / 组合10 / 掉出10名才换


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def now_str():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def price_of(prices, code):
    p = prices.get(code) or {}
    v = p.get("current_close", p.get("close"))
    return v if isinstance(v, (int, float)) and v > 0 else None


def ladder_tier(mkt):
    """宏观阶梯档位: 2=熊市保护(核心减半) / 1=门控(卫星现金) / 0=正常满配"""
    dd = mkt.get("drawdown_from_52w_high_pct")
    if isinstance(dd, (int, float)) and dd <= -20:
        return 2
    if mkt.get("buy_gate_active"):
        return 1
    return 0


TIER_DESC = {0: "正常 (核心80% + 卫星20%)", 1: "宏观门控 (核心80%, 卫星舱现金)", 2: "熊市保护 (核心减半40%, 其余现金)"}


def run_market(mk):
    cfg = CONFIG[mk]
    state = load(cfg["state"])
    scores = load(D("model_scores.json"))
    if not state or not scores:
        print(f"[{cfg['label']}] 缺少扫描状态或评分文件, 跳过")
        return
    ranked = scores["a" if mk == "a" else "us"]
    prices = state.get("prices") or {}
    mkt = state.get("market") if isinstance(state.get("market"), dict) else {}

    book = load(cfg["book"]) or dict(
        cash=cfg["initial"], initialCash=cfg["initial"], currency=cfg["cur"],
        positions={}, history=[], snapshots=[], decisions=[],
        strategy_state=dict(tier=None, seeded=False))
    ss = book.setdefault("strategy_state", {})
    pos = book["positions"]

    bar_closed = is_last_weekly_bar_closed(mk)
    tier = ladder_tier(mkt)
    rank_of = {r["code"]: r["rank"] for r in ranked}
    weight_of = {r["code"]: r["weight"] for r in ranked}
    name_of = {r["code"]: r["name"] for r in ranked}

    # 建仓资格: 有行情 + 本周收盘不低于周线 EMA21
    def entry_ok(code):
        p = prices.get(code) or {}
        px, e21 = price_of(prices, code), p.get("ema21")
        return px is not None and (not isinstance(e21, (int, float)) or px >= e21)

    # 合格池有效排名: 先剔除 EMA21 下方的, 再按模型排名排队。
    # 排名缓冲和"收复回归"都基于有效排名 —— 高排名股票收复 EMA21 后会把
    # 第 10 名的有效排名挤成 11, 从而触发换仓把它接回来。
    eligible = [r["code"] for r in ranked if entry_ok(r["code"])]
    eff_rank = {c: i + 1 for i, c in enumerate(eligible)}

    # ---- 触发检测 ----
    reasons, force_daily = [], False
    if not ss.get("seeded"):
        reasons.append("初始建仓 (账本为空, 按最近周线收盘价、当前排名与宏观档位建立组合)")
        force_daily = True  # 初始建仓不等周五, 按最近一根已完成周线的收盘价成交
    if ss.get("tier") is not None and tier != ss.get("tier"):
        reasons.append(f"宏观阶梯变档: {TIER_DESC.get(ss.get('tier'),'?')} → {TIER_DESC[tier]}"
                       + (f" [距52周高点 {mkt.get('drawdown_from_52w_high_pct')}%]" if tier == 2 else ""))
        if tier == 2:
            force_daily = True  # 熊市保护当日执行
    broken = []
    for code in list(pos):
        p = prices.get(code) or {}
        px, e21 = price_of(prices, code), p.get("ema21")
        if px is not None and isinstance(e21, (int, float)) and px < e21:
            broken.append(code)
    if broken:
        reasons.append("持仓周线收盘跌破 EMA21 (核心趋势破坏): "
                       + " / ".join(f"{(pos[c].get('name') or c)}({c})" for c in broken))
    dropped = [c for c in pos if eff_rank.get(c, 999) > RANK_EXIT]
    if dropped:
        incoming = [c for c in eligible[:RANK_EXIT] if c not in pos]
        msg = ("持仓掉出合格排名 Top10 (排名缓冲触发): "
               + " / ".join(f"{(pos[c].get('name') or c)}(有效排名 {eff_rank.get(c, '已出合格池')})" for c in dropped))
        if incoming:
            msg += " ← 顶替者: " + " / ".join(
                f"{name_of.get(c, c)}(模型#{rank_of.get(c, '?')}, 收复EMA21回到合格池)" for c in incoming)
        reasons.append(msg)

    # ---- 快照 (每日, 不论是否交易) ----
    def equity():
        mv = sum((price_of(prices, c) or p["avgCost"]) * p["qty"] for c, p in pos.items())
        return book["cash"] + mv, mv

    total, mv = equity()
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    snaps = book["snapshots"]
    if snaps and snaps[-1]["date"] == today:
        snaps[-1].update(total=round(total, 2), cash=round(book["cash"], 2), mv=round(mv, 2))
    else:
        snaps.append(dict(date=today, total=round(total, 2), cash=round(book["cash"], 2), mv=round(mv, 2)))
        if len(snaps) > 730:
            del snaps[:len(snaps) - 730]

    events = []
    if reasons and (bar_closed or force_daily):
        # ---- 全量重定向到目标组合 (与一键建仓同语义) ----
        core_pct = 0.40 if tier == 2 else 0.80
        sat_pct = 0.20 if tier == 0 else 0.0
        core = eligible[:TOP_CORE]
        satellite = eligible[TOP_CORE:TOP_ALL] if sat_pct > 0 else []
        if len(core) < TOP_CORE:
            events.append(f"⚠ 合格标的不足 {TOP_CORE} 只 (EMA21 上方仅 {len(core)} 只), 本次仅持有合格者, 其余现金")

        # 目标市值
        target = {}
        for basket, pct in ((core, core_pct), (satellite, sat_pct)):
            if not basket or pct <= 0:
                continue
            wsum = sum(weight_of.get(c, 1) for c in basket) or 1
            for c in basket:
                target[c] = total * pct * weight_of.get(c, 1) / wsum

        # 卖出: 不在目标里的持仓 → 清仓; 在目标里的做差额调整
        lot = cfg["lot"]
        trades = []
        for code in list(pos):
            px = price_of(prices, code)
            if px is None:
                continue  # 无行情不动
            if code not in target:
                qty = pos[code]["qty"]
                book["cash"] += qty * px
                trades.append(("sell", code, pos[code].get("name") or code, qty, px))
                del pos[code]
        # 买入/调整: 先算整手, 再篮子内贪心补
        plan = []
        for code, tv in target.items():
            px = price_of(prices, code)
            if px is None:
                continue
            cur_qty = pos.get(code, {}).get("qty", 0)
            want_qty = int(tv / px / lot) * lot
            plan.append([code, px, tv, cur_qty, want_qty])
        # 贪心: 用剩余预算把缺口最大的加一手 (预算 = 目标总投入)
        budget = sum(tv for _, _, tv, _, _ in plan)
        spent = sum(px * wq for _, px, _, _, wq in plan)
        while True:
            best = None
            for row in plan:
                code, px, tv, cq, wq = row
                short = tv - wq * px
                if spent + px * lot > budget or short <= px * lot / 2:
                    continue
                if not best or short > best[1]:
                    best = (row, short)
            if not best:
                break
            best[0][4] += lot
            spent += best[0][1] * lot
        for code, px, tv, cur_qty, want_qty in plan:
            diff = want_qty - cur_qty
            if diff == 0:
                continue
            nm = name_of.get(code) or (prices.get(code) or {}).get("name") or code
            if diff > 0:
                cost = diff * px
                if cost > book["cash"] + 1e-6:
                    continue
                book["cash"] -= cost
                p0 = pos.get(code)
                if p0:
                    p0["avgCost"] = (p0["avgCost"] * p0["qty"] + cost) / (p0["qty"] + diff)
                    p0["qty"] += diff
                else:
                    pos[code] = dict(qty=diff, avgCost=px, name=nm)
                trades.append(("buy", code, nm, diff, px))
            else:
                book["cash"] += -diff * px
                pos[code]["qty"] += diff
                if pos[code]["qty"] == 0:
                    del pos[code]
                trades.append(("sell", code, nm, -diff, px))

        ts = now_str()
        for side, code, nm, qty, px in trades:
            book["history"].insert(0, dict(ts=ts, side=side, code=code, name=nm,
                                           price=px, qty=qty, amount=round(qty * px, 2),
                                           cashAfter=round(book["cash"], 2)))
        if len(book["history"]) > 400:
            del book["history"][400:]

        total2, mv2 = equity()
        decision = dict(date=today, tier=TIER_DESC[tier], reasons=reasons,
                        trades=[f"{'买入' if s == 'buy' else '卖出'} {nm} {qty:,} 股 @ {px:.2f}" for s, code, nm, qty, px in trades],
                        holdings=[f"{p.get('name') or c} {rank_of.get(c, '?')}名" for c, p in pos.items()],
                        cash_pct=round(book["cash"] / total2 * 100, 1) if total2 else 0)
        book["decisions"].insert(0, decision)
        if len(book["decisions"]) > 60:
            del book["decisions"][60:]
        ss["seeded"] = True
        if trades:
            events.append(f"🤖 {cfg['label']}模拟盘调仓 · {TIER_DESC[tier]}")
            events += [f"  原因: {r}" for r in reasons]
            events += [f"  {t}" for t in decision["trades"]]
            events.append(f"  调仓后: 持仓 {len(pos)} 只 / 现金 {decision['cash_pct']}% / 总资产 {cfg['cur']}{total2:,.0f}")
    elif reasons and not bar_closed:
        # 周中预警去重: 同样的待确认触发只推一次, 变化了才再推
        sig = "|".join(sorted(reasons))
        if ss.get("pending_sig") != sig:
            events.append(f"🤖 {cfg['label']}模拟盘: 检测到触发但周线未收盘, 等待周五收盘确认 — " + "；".join(reasons))
            ss["pending_sig"] = sig
    if bar_closed or not reasons:
        ss.pop("pending_sig", None)

    ss["tier"] = tier
    ss["last_check"] = now_str()
    save(cfg["book"], book)

    # 把事件写回扫描状态, 让 sender 推送
    if events:
        state.setdefault("changes", [])
        state["changes"] += events
    total3, mv3 = equity()
    state["portfolio_summary"] = dict(
        total=round(total3, 2), cash=round(book["cash"], 2),
        cash_pct=round(book["cash"] / total3 * 100, 1) if total3 else 0,
        pnl_pct=round((total3 - book["initialCash"]) / book["initialCash"] * 100, 2),
        positions=len(pos), tier=TIER_DESC[tier], currency=cfg["cur"],
        last_decision=(book["decisions"][0] if book["decisions"] else None))
    save(cfg["state"], state)
    print(f"[{cfg['label']}] tier={tier} bar_closed={bar_closed} 触发={len(reasons)} 交易事件={bool(events)} "
          f"总资产={cfg['cur']}{total3:,.0f} 现金={state['portfolio_summary']['cash_pct']}%")


if __name__ == "__main__":
    run_market("a")
    run_market("us")
