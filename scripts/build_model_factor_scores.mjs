#!/usr/bin/env node
// 重新生成 MODEL_FACTOR_SCORES.md — 与 index.html computeQuantWeights/computeQuantWeightsUS 同一套逻辑。
// 无外部依赖: node scripts/build_model_factor_scores.mjs
// 注意: 改模型时必须同步 index.html / outputs/factor_spreadsheet/build_latest_quant_factors.mjs / 本文件。
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

function aiExecutionScore(c) {
  return Number.isFinite(c && c.ai_execution_score) ? c.ai_execution_score : 5;
}

function getForwardRevenueEstimate(c) {
  const q2 = c && c.q2_outlook;
  if (q2 && Number.isFinite(q2.rev_estimate)) return q2.rev_estimate;
  const f = ((c && c.quarters) || []).find(q => q.src === "F" && Number.isFinite(q.rev));
  return f ? f.rev : null;
}

function revenueYoYSeries(qs) {
  const seq = [];
  for (let i = 4; i < qs.length; i++) {
    const prevYear = qs[i - 4].rev;
    seq.push(prevYear > 0 ? (qs[i].rev / prevYear - 1) * 100 : 0);
  }
  return seq;
}

function growthMomentumRaw(c) {
  const qs = ((c && c.quarters) || []).filter(q => Number.isFinite(q.rev));
  if (qs.length < 5) return { raw: 0, label: "历史不足" };
  const yoySeq = revenueYoYSeries(qs);
  const latestYoY = yoySeq[yoySeq.length - 1];
  let histAccel = yoySeq.length >= 2 ? latestYoY - yoySeq[yoySeq.length - 2] : null;
  let histKind = "同比加速";
  if (histAccel === null && qs.length >= 5) {
    const qoq = [];
    for (let i = 1; i < qs.length; i++) {
      if (qs[i - 1].rev > 0) qoq.push((qs[i].rev / qs[i - 1].rev - 1) * 100);
    }
    if (qoq.length >= 4) {
      histAccel = (qoq[qoq.length - 1] + qoq[qoq.length - 2]) / 2 - (qoq[0] + qoq[1]) / 2;
      histKind = "环比加速(5季)";
    }
  }
  const fwd = getForwardRevenueEstimate(c);
  let fwdYoY = null, fwdAccel = null;
  if (Number.isFinite(fwd) && qs[qs.length - 1].rev > 0) {
    const priorYear = qs[qs.length - 4] && qs[qs.length - 4].rev;
    if (priorYear > 0) {
      fwdYoY = (fwd / priorYear - 1) * 100;
      fwdAccel = fwdYoY - latestYoY;
    }
  }
  let raw = 0;
  if (Number.isFinite(histAccel) && Number.isFinite(fwdAccel)) raw = 0.70 * histAccel + 0.30 * fwdAccel;
  else if (Number.isFinite(histAccel)) raw = histAccel;
  else if (Number.isFinite(fwdAccel)) raw = fwdAccel;
  const label = (Number.isFinite(histAccel) ? `${histKind} ${histAccel.toFixed(1)}ppt` : "加速度 历史不足")
    + (Number.isFinite(fwdAccel) ? ` / 前瞻 ${fwdAccel.toFixed(1)}ppt` : " / 无forecast不扣分");
  return { raw: clamp(raw, -100, 100), latestYoY, histAccel, fwdAccel, label };
}

function latestRevenueYoY(c) {
  const qs = ((c && c.quarters) || []).filter(q => Number.isFinite(q.rev));
  if (qs.length < 5) return 0;
  const base = qs[qs.length - 5].rev;
  return base > 0 ? (qs[qs.length - 1].rev / base - 1) * 100 : 0;
}

function categoryCycleRisk(code, c) {
  const codeRisk = {
    MU: 1.00, SNDK: 1.00,
    LITE: 0.75, COHR: 0.70, FN: 0.65, CIEN: 0.55, GLW: 0.45, CRDO: 0.55, ALAB: 0.45,
    AMAT: 0.55, KLAC: 0.45, LRCX: 0.55, ONTO: 0.50, ASML: 0.40, TER: 0.45,
    ASE: 0.55, AMKR: 0.60, AMD: 0.35, MRVL: 0.35, INTC: 0.35,
    CCJ: 0.60, NRG: 0.45, VST: 0.35
  };
  if (codeRisk[code] !== undefined) return codeRisk[code];
  const catRisk = {
    memory: 1.00, packaging: 0.55, foundry: 0.45, network: 0.40,
    core_chip: 0.25, power: 0.25, dc_infra: 0.20, hyperscaler: 0.10,
    app: 0.35, base: 0.45, infra: 0.40, hw: 0.35, core: 0.25
  };
  return catRisk[c && c.cat] || 0.20;
}

function downstreamCapexExposure(code, c) {
  if (!c) return 0;
  if (["MSFT", "GOOGL", "AMZN", "META", "AAPL", "ORCL"].includes(code)) return 0;
  if (["memory", "core_chip", "foundry", "network", "packaging", "dc_infra"].includes(c.cat)) return 1;
  if (["infra", "base", "hw", "core"].includes(c.cat)) return 0.6;
  return 0.25;
}

function capexStressFromMetrics(qm) {
  if (!qm) return 0;
  const ocf = qm.operating_cash_flow_billion;
  const capex = qm.capex_billion;
  if (!Number.isFinite(ocf) || !Number.isFinite(capex)) return 0.2;
  if (ocf <= 0) return Number.isFinite(capex) && capex > 0 ? 1.2 : 0.6;
  const ratio = capex / ocf;
  const fcfMargin = Number.isFinite(qm.fcf_margin_pct) ? qm.fcf_margin_pct : 0;
  const stressFloor = fcfMargin >= 15 ? 0.80 : 0.50;
  return clamp(ratio - stressFloor, 0, 1.5);
}

function valuationExpectationRisk(c) {
  if (!c) return 0;
  const qs = (c.quarters || []).filter(q => Number.isFinite(q.rev));
  const ttmRev = qs.slice(-4).reduce((s, q) => s + q.rev, 0);
  const mc = c.market_cap_billion || 0;
  const qm = c.quality_metrics || {};
  const fcf = Number.isFinite(qm.free_cash_flow_billion) ? qm.free_cash_flow_billion : null;
  const priceToSales = ttmRev > 0 ? mc / ttmRev : null;
  const priceToFcf = fcf > 0 ? (mc / 10) / fcf : null;
  const psRisk = Number.isFinite(priceToSales) ? clamp((priceToSales - 20) / 50, 0, 1.5) : 0;
  const fcfRisk = Number.isFinite(priceToFcf) ? clamp((priceToFcf - 60) / 180, 0, 1.2) : 0;
  const raw = Math.max(psRisk, fcfRisk);
  if (c.cat === "app") return raw;
  if (c.cat === "core_chip") return raw * (Number.isFinite(fcf) && fcf < 2 ? 0.70 : 0.25);
  if (c.cat === "hyperscaler") return raw * 0.25;
  return raw * 0.15;
}

function computeHyperscalerFundingStress(dataset) {
  const names = ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "AAPL", "CRWV"];
  const vals = names
    .filter(code => dataset[code] && dataset[code].quality_metrics)
    .map(code => capexStressFromMetrics(dataset[code].quality_metrics))
    .filter(Number.isFinite);
  if (!vals.length) return 0;
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  return clamp((avg - 0.25) / 0.55, 0, 1.5);
}

function durabilityRaw(c) {
  const qm = c.quality_metrics || {};
  const mc = c.market_cap_billion || 100;
  const fcf = Number.isFinite(qm.free_cash_flow_billion) ? qm.free_cash_flow_billion : 0;
  const recentRev = ((c.quarters || []).slice(-4).reduce((s, q) => s + (Number.isFinite(q.rev) ? q.rev : 0), 0)) / 10;
  const fcfMargin = recentRev > 0 ? (fcf / recentRev * 100) : (Number.isFinite(qm.fcf_margin_pct) ? qm.fcf_margin_pct : 0);
  const netCash = Number.isFinite(qm.net_cash_billion) ? qm.net_cash_billion : 0;
  const netCashToMC = netCash / Math.max(mc / 10, 0.1);
  return Math.log(mc) + 0.08 * clamp(fcfMargin, -25, 35) + 0.18 * Math.log1p(Math.max(fcf, 0)) + 0.6 * clamp(netCashToMC, -0.4, 0.4);
}

function turnoverRiskScore(t, market) {
  if (!Number.isFinite(t) || t <= 0) return market === "us" ? 0 : -0.3;
  if (t < 1 && market !== "us") return -Math.log(1 / t);
  if (t > 10) return -Math.log(t / 10);
  return 0;
}

function zscore(values) {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((a, b) => a + (b - mean) * (b - mean), 0) / values.length;
  const std = Math.sqrt(variance) || 1;
  return values.map(v => clamp((v - mean) / std, -2, 2));
}

function computeDataset(dataset, market) {
  const codes = Object.keys(dataset).filter(code => !code.startsWith("_"));
  const valid = codes.filter(code => {
    const c = dataset[code];
    return c && c.quarters && c.quarters.length >= 5
      && c.quarters.every(q => q.rev !== null && q.gm !== null && q.nm !== null);
  });
  const isUS = market === "US";
  const hyperscalerFundingStress = isUS ? computeHyperscalerFundingStress(dataset) : 0;
  const raw = valid.map(code => {
    const c = dataset[code];
    const qs = c.quarters;
    const revYoY = latestRevenueYoY(c);
    const gmLatest = qs[qs.length - 1].gm;
    const nmLatest = qs[qs.length - 1].nm;
    const gmPrev = qs.length >= 2 ? qs[qs.length - 2].gm : gmLatest;
    const nmPrev = qs.length >= 2 ? qs[qs.length - 2].nm : nmLatest;
    const marginTrend = (gmLatest - gmPrev) * 0.6 + (nmLatest - nmPrev) * 0.4;
    const momentum = growthMomentumRaw(c);
    const baseCycleRisk = categoryCycleRisk(code, c);
    const extremeGrowthPenalty = Math.max(0, (revYoY - 80) / 120);
    const marginExpansionPenalty = Math.max(0, marginTrend / 8);
    const capexStress = isUS ? capexStressFromMetrics(c.quality_metrics) : 0;
    const downstreamStress = isUS ? downstreamCapexExposure(code, c) * hyperscalerFundingStress : 0;
    const valuationRisk = valuationExpectationRisk(c);
    const cyclePenalty = baseCycleRisk + extremeGrowthPenalty * baseCycleRisk + marginExpansionPenalty * 0.35
      + downstreamStress * 0.45 + capexStress * baseCycleRisk * 0.25 + valuationRisk * 0.45;
    const qm = c.quality_metrics || {};
    return {
      code, name: c.name || code,
      strategic: (c.strategic || 5) / 10,
      aiExecution: aiExecutionScore(c) / 10,
      logMC: Math.log(c.market_cap_billion || 100),
      marketCap: c.market_cap_billion || null,
      revYoY: clamp(revYoY, -50, 300),
      gm: gmLatest, nm: nmLatest, nmClipped: clamp(nmLatest, -30, 60),
      momentum: momentum.raw, momentumLabel: momentum.label,
      turnoverScore: turnoverRiskScore(c.avg_turnover_pct || 3, isUS ? "us" : "a"),
      durability: durabilityRaw(c),
      cyclePenalty,
      fcf: Number.isFinite(qm.free_cash_flow_billion) ? qm.free_cash_flow_billion : null,
      fcfMargin: Number.isFinite(qm.fcf_margin_pct) ? qm.fcf_margin_pct : null,
      hasForecast: Number.isFinite(getForwardRevenueEstimate(c)),
      hyperscalerFundingStress
    };
  });
  if (raw.length < 4) return { rows: [], hyperscalerFundingStress };
  const zGrow = zscore(raw.map(r => r.revYoY));
  const zGM = zscore(raw.map(r => r.gm));
  const zNM = zscore(raw.map(r => r.nmClipped));
  const zMOM = zscore(raw.map(r => r.momentum));
  const zDUR = zscore(raw.map(r => r.durability));
  const zRISK = zscore(raw.map(r => -r.cyclePenalty + 0.10 * r.turnoverScore));
  const zProfit = raw.map((_, i) => 0.6 * zGM[i] + 0.4 * zNM[i]);
  const W = { strategic: 0.12, aiExecution: 0.10, growth: 0.20, profit: 0.20, durability: 0.18, risk: 0.20 };
  const rows = raw.map((r, i) => ({
    ...r,
    contribStrategic: W.strategic * r.strategic * 2,
    contribAiExecution: W.aiExecution * r.aiExecution * 2,
    contribGrowth: W.growth * (0.65 * zGrow[i] + 0.35 * zMOM[i]),
    contribProfit: W.profit * zProfit[i],
    contribDurability: W.durability * zDUR[i],
    contribRisk: W.risk * zRISK[i],
    score: W.growth * (0.65 * zGrow[i] + 0.35 * zMOM[i]) + W.profit * zProfit[i] + W.durability * zDUR[i]
      + W.risk * zRISK[i] + W.strategic * r.strategic * 2 + W.aiExecution * r.aiExecution * 2
  })).sort((a, b) => b.score - a.score);
  const minComp = Math.min(...rows.map(r => r.score));
  const shifted = rows.map(r => r.score - minComp + 0.5);
  const sum = shifted.reduce((a, b) => a + b, 0);
  rows.forEach((r, i) => { r.weight = Math.round(shifted[i] / sum * 1000) / 10; r.rank = i + 1; });
  return { rows, hyperscalerFundingStress };
}

const fmt = (n, d = 3) => Number.isFinite(n) ? n.toFixed(d) : "";
const pct = n => Number.isFinite(n) ? `${n.toFixed(1)}%` : "";

function tableFor(rows) {
  const head = "| 排名 | 代码 | 名称 | 权重% | 总分 | 主题 | AI执行 | 增长动能 | 盈利质量 | 规模现金流 | 周期资金风险 | 收入YoY | 加速度 | GM/NM | 市值 | FCF(B$) | FCF率 | 周期惩罚 | Forecast |\n"
    + "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|";
  const body = rows.map(r =>
    `| ${r.rank} | ${r.code} | ${r.name} | ${fmt(r.weight, 1)} | ${fmt(r.score)} | ${fmt(r.contribStrategic)} | ${fmt(r.contribAiExecution)} | ${fmt(r.contribGrowth)} | ${fmt(r.contribProfit)} | ${fmt(r.contribDurability)} | ${fmt(r.contribRisk)} | ${pct(r.revYoY)} | ${r.momentumLabel} | ${pct(r.gm)} / ${pct(r.nm)} | ${r.marketCap ?? ""} | ${fmt(r.fcf, 1)} | ${pct(r.fcfMargin)} | ${fmt(r.cyclePenalty, 2)} | ${r.hasForecast ? "有" : "无"} |`
  ).join("\n");
  return head + "\n" + body;
}

const companiesA = JSON.parse(await fs.readFile(path.join(ROOT, "data/companies.json"), "utf8"));
const companiesUS = JSON.parse(await fs.readFile(path.join(ROOT, "data/companies_us.json"), "utf8"));
const a = computeDataset(companiesA, "A");
const us = computeDataset(companiesUS, "US");

const md = `# 最新量化模型因子得分

生成时间：${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })} HKT
生成方式：\`node scripts/build_model_factor_scores.mjs\`（与 index.html 模型逻辑同步；改模型请同步三处并重新生成本文件）

## 公式（6 因子，A股/美股一致）

总分 = 主题护城河 12% + AI执行 10% + 增长动能 20% + 盈利质量 20% + 规模现金流 18% + 周期资金风险 20%

\`\`\`text
主题护城河 = 0.12 × (strategic / 10) × 2
AI执行     = 0.10 × (ai_execution_score / 10) × 2   ；缺失时取中性 5 分（不回落 strategic，避免主题分双计）
增长动能   = 0.20 × (0.65 × z(收入YoY) + 0.35 × z(增长加速度))
盈利质量   = 0.20 × (0.60 × z(最新毛利率) + 0.40 × z(最新净利率，clip -30%~60%))
规模现金流 = 0.18 × z(durabilityRaw)
周期资金风险 = 0.20 × z(-cyclePenalty + 0.10 × turnoverScore)
权重% = (总分 - 最低总分 + 0.5) 在股票池内归一化到 100
\`\`\`

### 增长加速度

\`\`\`text
≥6 季数据：历史加速度 = 最新 YoY - 上一季 YoY（同比差分）
恰好 5 季：退回 QoQ 口径 = 最近两段环比增速均值 - 早期两段环比增速均值
有 forecast：加速度 = 70% × 历史加速度 + 30% × 前瞻加速度
无 forecast：只用历史加速度，不扣分（两种情况下历史加速度都存在，不会出现"有指引反而吃亏"）
\`\`\`

### durabilityRaw

\`\`\`text
durabilityRaw = log(市值亿$) + 0.08 × clip(FCF margin, -25, 35) + 0.18 × log1p(max(FCF, 0))
              + 0.6 × clip(netCash($B) / (市值亿$ ÷ 10), -0.4, 0.4)   ← 单位已对齐（旧版少除 10）
美股 FCF/netCash 来自 SEC Companyfacts 最新完整财年（fill_us_cash_flow_from_sec.py，含时效守卫）。
A 股暂无可靠 FCF 字段，该项主要体现市值耐久性。
\`\`\`

### cyclePenalty

\`\`\`text
cyclePenalty = 行业基础周期风险 + 超高 YoY 惩罚 + 利润率快速扩张惩罚
             + 下游资金压力传导 (仅美股) + CapEx/OCF 压力 (仅美股) + 估值预期风险
下游资金压力 = downstreamCapexExposure × hyperscalerFundingStress
hyperscalerFundingStress = clamp((avg(MSFT/GOOGL/AMZN/META/ORCL/AAPL/CRWV capex压力) - 0.25) / 0.55, 0, 1.5)
经营现金流为负的公司 capex 压力记 1.2（极端资金压力，不再是旧版的 0.2）。
当前美股 hyperscalerFundingStress = ${fmt(us.hyperscalerFundingStress, 3)}
\`\`\`

## A 股（${a.rows.length} 只具备完整 5 季合规数据）

${tableFor(a.rows)}

## 美股（${us.rows.length} 只具备完整 5 季合规数据）

${tableFor(us.rows)}
`;

await fs.writeFile(path.join(ROOT, "MODEL_FACTOR_SCORES.md"), md);
console.log(`MODEL_FACTOR_SCORES.md regenerated: A=${a.rows.length} US=${us.rows.length} hyperscalerStress=${fmt(us.hyperscalerFundingStress, 3)}`);
console.log("US Top5:", us.rows.slice(0, 5).map(r => `${r.code} ${fmt(r.score)}`).join(" / "));
console.log("A Top5:", a.rows.slice(0, 5).map(r => `${r.code} ${fmt(r.score)}`).join(" / "));
