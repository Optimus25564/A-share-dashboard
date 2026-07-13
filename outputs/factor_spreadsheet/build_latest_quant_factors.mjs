import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve("../..");
const outDir = path.resolve(".");
const outputPath = path.join(outDir, "latest_quant_factors.xlsx");
const asOf = new Date();

function subjectiveEffective(score, updatedStr){
  // 主观评分新鲜度衰减: ≤180天 全额, 180-365天 半衰向中性5, >365天/无日期 按陈旧处理
  const s = Number.isFinite(score) ? score : 5;
  if (!updatedStr) return 5 + (s - 5) * 0.5;
  const days = (Date.now() - new Date(updatedStr).getTime()) / 86400000;
  if (days <= 180) return s;
  if (days <= 365) return 5 + (s - 5) * 0.5;
  return 5;
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n));
}

function finite(n) {
  return Number.isFinite(n) ? n : null;
}

function fmtPct(n) {
  return Number.isFinite(n) ? n / 100 : null;
}

function aiExecutionScore(c) {
  // 缺失回落到中性 5, 不回落 strategic (避免主题分双计) — 与 index.html 保持一致
  return Number.isFinite(c && c.ai_execution_score) ? c.ai_execution_score : 5;
}

function latestQuarter(c) {
  const qs = c && c.quarters;
  return qs && qs.length ? qs[qs.length - 1] : null;
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
  if (qs.length < 5) {
    return { raw: 0, latestYoY: null, histAccel: null, fwdYoY: null, fwdAccel: null, label: "历史不足" };
  }
  const yoySeq = revenueYoYSeries(qs);
  const latestYoY = yoySeq[yoySeq.length - 1];
  // ≥6 季用 YoY 差分; 恰好 5 季退回 QoQ 均值差 — 与 index.html 保持一致
  let histAccel = yoySeq.length >= 2 ? latestYoY - yoySeq[yoySeq.length - 2] : null;
  if (histAccel === null && qs.length >= 5) {
    const qoq = [];
    for (let i = 1; i < qs.length; i++) {
      if (qs[i - 1].rev > 0) qoq.push((qs[i].rev / qs[i - 1].rev - 1) * 100);
    }
    if (qoq.length >= 4) {
      histAccel = (qoq[qoq.length - 1] + qoq[qoq.length - 2]) / 2 - (qoq[0] + qoq[1]) / 2;
    }
  }
  const fwd = getForwardRevenueEstimate(c);
  let fwdYoY = null;
  let fwdAccel = null;
  if (Number.isFinite(fwd)) {
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

  const parts = [`收入同比 ${latestYoY.toFixed(1)}%`];
  parts.push(Number.isFinite(histAccel) ? `同比加速 ${histAccel.toFixed(1)}ppt` : "同比加速 历史不足");
  parts.push(Number.isFinite(fwdYoY) && Number.isFinite(fwdAccel)
    ? `指引同比 ${fwdYoY.toFixed(1)}% / 指引加速 ${fwdAccel.toFixed(1)}ppt`
    : "无forecast不扣分");

  return { raw: clamp(raw, -100, 100), latestYoY, histAccel, fwdYoY, fwdAccel, label: parts.join(" / ") };
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
  if (ocf <= 0) return Number.isFinite(capex) && capex > 0 ? 1.2 : 0.6;  // 负经营现金流 = 极端资金压力
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
  return clamp((avg - 0.25) / 0.55, 0, 1.5);  // 阈值 0.25, 校准见 index.html 同名函数注释
}

function durabilityRaw(c) {
  const qm = c.quality_metrics || {};
  const mc = c.market_cap_billion || 100;
  const fcf = Number.isFinite(qm.free_cash_flow_billion) ? qm.free_cash_flow_billion : 0;
  const recentRev = ((c.quarters || []).slice(-4).reduce((s, q) => s + (Number.isFinite(q.rev) ? q.rev : 0), 0)) / 10;
  const fcfMargin = recentRev > 0 ? (fcf / recentRev * 100) : (Number.isFinite(qm.fcf_margin_pct) ? qm.fcf_margin_pct : 0);
  const netCash = Number.isFinite(qm.net_cash_billion) ? qm.net_cash_billion : 0;
  // net_cash 是 $B, market_cap_billion 是亿$ → /10 对齐单位 (修复 10 倍低估)
  const netCashToMC = netCash / Math.max(mc / 10, 0.1);
  return Math.log(mc) + 0.08 * clamp(fcfMargin, -25, 35) + 0.18 * Math.log1p(Math.max(fcf, 0)) + 0.6 * clamp(netCashToMC, -0.4, 0.4);
}

function turnoverRiskScore(t, market) {
  if (!Number.isFinite(t) || t <= 0) return market === "us" ? 0 : -0.3;
  if (t < 1 && market !== "us") return -Math.log(1 / t);  // 低换手惩罚只适用 A 股
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
  const hyperscalerFundingStress = market === "US" ? computeHyperscalerFundingStress(dataset) : 0;
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
    const capexStress = market === "US" ? capexStressFromMetrics(c.quality_metrics) : 0;
    const downstreamStress = market === "US" ? downstreamCapexExposure(code, c) * hyperscalerFundingStress : 0;
    const valuationRisk = valuationExpectationRisk(c);
    const cyclePenalty = baseCycleRisk
      + extremeGrowthPenalty * baseCycleRisk
      + marginExpansionPenalty * 0.35
      + downstreamStress * 0.45
      + capexStress * baseCycleRisk * 0.25
      + valuationRisk * 0.45;
    const qm = c.quality_metrics || {};
    const recentRev = ((c.quarters || []).slice(-4).reduce((s, q) => s + (Number.isFinite(q.rev) ? q.rev : 0), 0)) / 10;
    const fcf = Number.isFinite(qm.free_cash_flow_billion) ? qm.free_cash_flow_billion : null;
    const fcfMarginComputed = recentRev > 0 && Number.isFinite(fcf) ? fcf / recentRev * 100 : null;
    const netCash = Number.isFinite(qm.net_cash_billion) ? qm.net_cash_billion : null;
    return {
      market,
      code,
      name: c.name || code,
      cat: c.cat || "",
      strategic: subjectiveEffective(c.strategic, c.strategic_updated),
      aiExecution: aiExecutionScore(c),
      aiExecutionNote: c.ai_execution_note || "",
      marketCap: c.market_cap_billion || null,
      logMC: Math.log(c.market_cap_billion || 100),
      latestQuarter: latestQuarter(c)?.q || "",
      revYoY: clamp(revYoY, -50, 300),
      revYoYRaw: revYoY,
      gm: gmLatest,
      nm: nmLatest,
      nmClipped: clamp(nmLatest, -30, 60),
      marginTrend,
      momentum: momentum.raw,
      latestYoY: momentum.latestYoY,
      histAccel: momentum.histAccel,
      fwdYoY: momentum.fwdYoY,
      fwdAccel: momentum.fwdAccel,
      fwdRevEstimate: getForwardRevenueEstimate(c),
      momentumLabel: momentum.label,
      turnoverRaw: c.avg_turnover_pct || 3,
      turnoverScore: turnoverRiskScore(c.avg_turnover_pct || 3, market === "US" ? "us" : "a"),
      durability: durabilityRaw(c),
      baseCycleRisk,
      extremeGrowthPenalty,
      marginExpansionPenalty,
      downstreamStress,
      capexStress,
      valuationRisk,
      hyperscalerFundingStress,
      cyclePenalty,
      fcf,
      fcfMarginStored: finite(qm.fcf_margin_pct),
      fcfMarginComputed,
      netCash,
      netCashToMC: Number.isFinite(netCash) && c.market_cap_billion ? netCash / (c.market_cap_billion / 10) : null,
      ocf: finite(qm.operating_cash_flow_billion),
      capex: finite(qm.capex_billion),
      quarters: c.quarters || [],
      outlook: c.q2_outlook || {}
    };
  });

  const zGrow = zscore(raw.map(r => r.revYoY));
  const zGM = zscore(raw.map(r => r.gm));
  const zNM = zscore(raw.map(r => r.nmClipped));
  const zMOM = zscore(raw.map(r => r.momentum));
  const zDUR = zscore(raw.map(r => r.durability));
  const zRISK = zscore(raw.map(r => -r.cyclePenalty + 0.10 * r.turnoverScore));
  const zProfit = raw.map((_, i) => 0.6 * zGM[i] + 0.4 * zNM[i]);
  const W = { strategic: 0.10, aiExecution: 0.00, growth: 0.26, profit: 0.26, durability: 0.18, risk: 0.20 };  // 主观仅主题10%且带新鲜度衰减; AI执行退役为参考字段 (2026-07-14 A/B回测后调整)
  const rows = raw.map((r, i) => {
    const growthComposite = 0.65 * zGrow[i] + 0.35 * zMOM[i];
    const contribGrowth = W.growth * growthComposite;
    const contribProfit = W.profit * zProfit[i];
    const contribDurability = W.durability * zDUR[i];
    const contribRisk = W.risk * zRISK[i];
    const contribStrategic = W.strategic * (r.strategic / 10) * 2;
    const contribAiExecution = W.aiExecution * (r.aiExecution / 10) * 2;
    return {
      ...r,
      zGrow: zGrow[i],
      zMomentum: zMOM[i],
      zGrowthComposite: growthComposite,
      zGM: zGM[i],
      zNM: zNM[i],
      zProfit: zProfit[i],
      zDurability: zDUR[i],
      zRisk: zRISK[i],
      contribGrowth,
      contribProfit,
      contribDurability,
      contribRisk,
      contribStrategic,
      contribAiExecution,
      score: contribGrowth + contribProfit + contribDurability + contribRisk + contribStrategic + contribAiExecution
    };
  }).sort((a, b) => b.score - a.score);

  const minComp = Math.min(...rows.map(r => r.score));
  const shifted = rows.map(r => r.score - minComp + 0.5);
  const sum = shifted.reduce((a, b) => a + b, 0);
  let weights = shifted.map(s => Math.round(s / sum * 1000) / 10);
  const total = weights.reduce((a, b) => a + b, 0);
  const maxIdx = weights.indexOf(Math.max(...weights));
  if (maxIdx >= 0) weights[maxIdx] += Math.round((100 - total) * 10) / 10;
  rows.forEach((r, i) => {
    r.rank = i + 1;
    r.rawWeight = weights[i];
    if (i < 5) r.sleeve = "Core";
    else if (i < 10) r.sleeve = "Satellite";
    else r.sleeve = "";
  });
  const coreSum = rows.slice(0, 5).reduce((s, r) => s + r.rawWeight, 0);
  const satelliteSum = rows.slice(5, 10).reduce((s, r) => s + r.rawWeight, 0);
  rows.forEach((r, i) => {
    if (i < 5) r.portfolioWeight = coreSum > 0 ? r.rawWeight / coreSum * 80 : null;
    else if (i < 10) r.portfolioWeight = satelliteSum > 0 ? r.rawWeight / satelliteSum * 20 : null;
    else r.portfolioWeight = null;
  });
  return rows;
}

function addSheet(workbook, name, rows, widths = []) {
  const sheet = workbook.worksheets.add(name);
  sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length).values = rows;
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getUsedRange();
  used.format.font.name = "Aptos";
  used.format.font.size = 10;
  const header = sheet.getRangeByIndexes(0, 0, 1, rows[0].length);
  header.format.fill.color = "#17365D";
  header.format.font.color = "#FFFFFF";
  header.format.font.bold = true;
  header.format.horizontalAlignment = "Center";
  sheet.showGridlines = false;
  widths.forEach((w, i) => {
    if (w) sheet.getRangeByIndexes(0, i, rows.length, 1).format.columnWidthPx = w;
  });
  return sheet;
}

function detailRows(rows) {
  const headers = [
    "Rank", "Code", "Name", "Category", "Score", "Raw Weight %", "Sleeve", "Portfolio Weight %",
    "Strategic /10", "AI Execution /10", "AI Execution Note", "Latest Q", "Revenue YoY", "Growth Momentum Raw ppt", "Hist Accel ppt",
    "Forecast YoY", "Forecast Accel ppt", "Forecast Rev Estimate", "GM", "NM", "Margin Trend ppt",
    "Market Cap", "FCF", "FCF Margin Computed", "FCF Margin Stored", "Net Cash", "Net Cash / MC",
    "OCF", "Capex", "Capex Stress", "Valuation Expectation Risk", "Base Cycle Risk", "Downstream Stress", "Cycle Penalty",
    "Turnover %", "Turnover Risk Raw", "z Growth", "z Momentum", "z Growth Composite", "z GM", "z NM",
    "z Profit", "z Durability", "z Risk", "Growth Contrib", "Profit Contrib", "Durability Contrib",
    "Risk Contrib", "Strategic Contrib", "AI Execution Contrib", "Momentum Label"
  ];
  const body = rows.map(r => [
    r.rank, r.code, r.name, r.cat, r.score, r.rawWeight, r.sleeve, r.portfolioWeight,
    r.strategic, r.aiExecution, r.aiExecutionNote, r.latestQuarter, fmtPct(r.revYoY), r.momentum, r.histAccel,
    fmtPct(r.fwdYoY), r.fwdAccel, r.fwdRevEstimate, fmtPct(r.gm), fmtPct(r.nm), r.marginTrend,
    r.marketCap, r.fcf, fmtPct(r.fcfMarginComputed), fmtPct(r.fcfMarginStored), r.netCash, r.netCashToMC,
    r.ocf, r.capex, r.capexStress, r.valuationRisk, r.baseCycleRisk, r.downstreamStress, r.cyclePenalty,
    fmtPct(r.turnoverRaw), r.turnoverScore, r.zGrow, r.zMomentum, r.zGrowthComposite, r.zGM, r.zNM,
    r.zProfit, r.zDurability, r.zRisk, r.contribGrowth, r.contribProfit, r.contribDurability,
    r.contribRisk, r.contribStrategic, r.contribAiExecution, r.momentumLabel
  ]);
  return [headers, ...body];
}

function rawInputRows(market, dataset) {
  const rows = [[
    "Market", "Code", "Name", "Category", "Strategic /10", "AI Execution /10", "AI Execution Note", "Market Cap", "Avg Turnover %",
    "Quarter", "Rev", "GM", "NM", "Source", "Forecast Rev Estimate", "Forecast Notes",
    "FCF", "FCF Margin", "Net Cash", "OCF", "Capex"
  ]];
  Object.keys(dataset).filter(k => !k.startsWith("_")).sort().forEach(code => {
    const c = dataset[code];
    const qs = c.quarters && c.quarters.length ? c.quarters : [{}];
    qs.forEach(q => {
      rows.push([
        market, code, c.name || code, c.cat || "", c.strategic || null, aiExecutionScore(c), c.ai_execution_note || "", c.market_cap_billion || null,
        c.avg_turnover_pct || null, q.q || "", q.rev ?? null, fmtPct(q.gm), fmtPct(q.nm), q.src || "",
        getForwardRevenueEstimate(c), c.q2_outlook?.note || c.q2_outlook?.source || "",
        c.quality_metrics?.free_cash_flow_billion ?? null,
        fmtPct(c.quality_metrics?.fcf_margin_pct),
        c.quality_metrics?.net_cash_billion ?? null,
        c.quality_metrics?.operating_cash_flow_billion ?? null,
        c.quality_metrics?.capex_billion ?? null
      ]);
    });
  });
  return rows;
}

function formatNumeric(sheet, rows, cols, fmt) {
  for (const col of cols) {
    sheet.getRangeByIndexes(1, col, rows - 1, 1).numberFormat = fmt;
  }
}

function applyDetailFormats(sheet, rowCount) {
  formatNumeric(sheet, rowCount, [4, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48], "0.000");
  formatNumeric(sheet, rowCount, [5, 7], "0.0");
  formatNumeric(sheet, rowCount, [12, 15, 18, 19, 23, 24, 26, 33], "0.0%");
  formatNumeric(sheet, rowCount, [8, 9, 13, 14, 16, 20, 29, 30, 31, 32, 34], "0.0");
  formatNumeric(sheet, rowCount, [17, 21, 22, 25, 27, 28], "#,##0.0");
}

const companiesA = JSON.parse(await fs.readFile(path.join(root, "data/companies.json"), "utf8"));
const companiesUS = JSON.parse(await fs.readFile(path.join(root, "data/companies_us.json"), "utf8"));
const aRows = computeDataset(companiesA, "A");
const usRows = computeDataset(companiesUS, "US");

const workbook = Workbook.create();
const summaryRows = [
  ["最新量化因子总览", "", "", "", "", "", "", ""],
  ["生成时间", asOf.toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" }), "", "", "", "", "", ""],
  ["模型", "主题护城河10%(带衰减) + 增长动能26% + 盈利质量26% + 规模现金流18% + 周期/资金风险20% (AI执行已退役)", "", "", "", "", "", ""],
  ["Top10仓位规则", "Top5核心仓合计80%; #6-#10卫星仓合计20%; 每个篮子内部按原始权重归一", "", "", "", "", "", ""],
  ["", "", "", "", "", "", "", ""],
  ["Market", "Rank", "Code", "Name", "Score", "Raw Weight %", "Sleeve", "Portfolio Weight %"],
  ...usRows.slice(0, 10).map(r => ["US", r.rank, r.code, r.name, r.score, r.rawWeight, r.sleeve, r.portfolioWeight]),
  ["", "", "", "", "", "", "", ""],
  ...aRows.slice(0, 10).map(r => ["A", r.rank, r.code, r.name, r.score, r.rawWeight, r.sleeve, r.portfolioWeight])
];
const summary = addSheet(workbook, "Summary", summaryRows, [90, 70, 80, 190, 90, 100, 100, 120]);
summary.getRange("A1:H1").merge();
summary.getRange("A1").format.fill.color = "#102033";
summary.getRange("A1").format.font.color = "#FFFFFF";
summary.getRange("A1").format.font.bold = true;
summary.getRange("A1").format.font.size = 16;
formatNumeric(summary, summaryRows.length, [4], "0.000");
formatNumeric(summary, summaryRows.length, [5, 7], "0.0");

const usSheet = addSheet(workbook, "US Factors", detailRows(usRows), [
  55, 70, 170, 110, 75, 90, 90, 110, 90, 110, 360, 80, 95, 125, 105, 95, 120, 120,
  80, 80, 110, 95, 85, 120, 110, 85, 95, 80, 80, 85, 105, 115, 95, 85, 110,
  80, 90, 120, 70, 70, 80, 90, 70, 100, 95, 120, 90, 110, 115, 300
]);
applyDetailFormats(usSheet, usRows.length + 1);

const aSheet = addSheet(workbook, "A Factors", detailRows(aRows), [
  55, 80, 170, 90, 75, 90, 90, 110, 90, 110, 320, 80, 95, 125, 105, 95, 120, 120,
  80, 80, 110, 95, 85, 120, 110, 85, 95, 80, 80, 85, 105, 115, 95, 85, 110,
  80, 90, 120, 70, 70, 80, 90, 70, 100, 95, 120, 90, 110, 115, 300
]);
applyDetailFormats(aSheet, aRows.length + 1);

const rawSheet = addSheet(workbook, "Raw Inputs", [
  ...rawInputRows("US", companiesUS),
  ...rawInputRows("A", companiesA).slice(1)
], [70, 85, 170, 100, 90, 110, 360, 100, 100, 90, 90, 80, 80, 80, 130, 260, 80, 100, 90, 80, 80]);
formatNumeric(rawSheet, rawSheet.getUsedRange().rowCount, [8, 11, 12, 17], "0.0%");
formatNumeric(rawSheet, rawSheet.getUsedRange().rowCount, [7, 10, 14, 16, 18, 19, 20], "#,##0.0");

const formulaRows = [
  ["Section", "Formula / Definition"],
  ["Composite score", "Score = 0.20*(0.65*z(Revenue YoY)+0.35*z(Growth Momentum)) + 0.20*z(Profit) + 0.18*z(Durability) + 0.20*z(Risk) + 0.12*(Strategic/10*2) + 0.10*(AI Execution/10*2)"],
  ["AI Execution", "前瞻校正层: 模型/产品执行、AI变现路径、capex ROI风险、核心业务被AI改写风险。缺失时默认中性5分 (不回落Strategic, 避免主题分双计)。"],
  ["Growth Momentum", "历史加速和有来源forecast加速的混合: 0.70*历史加速 + 0.30*forecast加速; ≥6季历史加速=YoY差分, 恰好5季退回QoQ均值差; 没有forecast不扣分。"],
  ["Profit", "Profit z = 0.6*z(Gross Margin) + 0.4*z(Net Margin clipped -30% to 60%)."],
  ["Durability", "ln(Market Cap) + 0.08*clamp(FCF margin, -25, 35) + 0.18*ln(1+max(FCF,0)) + 0.6*clamp(Net Cash/Market Cap, -0.4, 0.4)."],
  ["Risk", "Risk input = -Cycle Penalty + 0.10*Turnover Risk Raw; 1%-10%换手不奖惩，低于1%或高于10%才惩罚。"],
  ["Cycle Penalty", "基础行业周期风险 + 极端增长惩罚 + 毛利/净利短期大幅扩张惩罚; 美股额外加入下游hyperscaler资金压力、公司capex stress和高估值预期风险。"],
  ["Valuation Expectation Risk", "用市值/TTM收入和市值/FCF衡量。应用层公司完整计入; hyperscaler/core_chip只计入25%, 其他产业链计入15%。"],
  ["Portfolio", "排名按Score，不按Raw Weight。Top5核心仓合计80%，#6-#10卫星仓合计20%，篮子内部按Raw Weight归一。"],
  ["Units", "美股 Market Cap/FCF/Net Cash/OCF/Capex 以十亿美元为主; A股按数据文件原单位展示。百分比列在Excel中用百分比格式显示。"]
];
addSheet(workbook, "Formula Notes", formulaRows, [190, 900]);

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  used.format.wrapText = false;
  used.format.verticalAlignment = "Middle";
}

const checks = [
  ["Check", "US", usRows.length],
  ["Check", "A", aRows.length],
  ["US Top 3", usRows.slice(0, 3).map(r => `${r.rank}.${r.code} ${r.score.toFixed(3)}`).join(" / "), ""],
  ["A Top 3", aRows.slice(0, 3).map(r => `${r.rank}.${r.code} ${r.score.toFixed(3)}`).join(" / "), ""]
];
addSheet(workbook, "Checks", checks, [120, 500, 100]);

const scan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan"
});
console.log(scan.ndjson);
console.log((await workbook.inspect({ kind: "table", range: "Summary!A1:H20", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 8 })).ndjson);
for (const sheetName of ["Summary", "US Factors", "A Factors", "Raw Inputs", "Formula Notes", "Checks"]) {
  await workbook.render({ sheetName, range: "A1:H20", scale: 1 });
}

await fs.mkdir(outDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
