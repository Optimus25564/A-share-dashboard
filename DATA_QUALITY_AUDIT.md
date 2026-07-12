# Data Quality Audit

审计时间：2026-06-06（2026-07-12 增补，见文末「2026-07-12 修复记录」）

结论：已按最新标准清洗。没有合规来源的财务数字已从 `rev/gm/nm` 模型字段移除，不能再影响量化排名、Top 5 或候选池。

完整机器审计结果见 `data_quality_audit.json`。

## 最新标准

- Actual 必须来自真实公告、公司 IR、SEC/监管披露或公司正式发布渠道。
- Forecast 必须来自公司 guidance、管理层公开 outlook 或明确可追溯的 consensus。
- Adjusted EBITDA、Non-GAAP operating margin 等关键盈利能力 forecast 可以保留，但必须单独标注口径，不能塞进 GAAP 毛利率/净利率字段。
- 没有来源就直接说没有。
- 没有合规来源的财务数字不得留在 `rev/gm/nm` 字段里。
- 无来源数据使用 `src: "NA"`，且 `rev/gm/nm` 必须为 `null`。

## 本轮执行动作

- 新增 `scripts/audit_data_quality.py`，用于重复审计 source 覆盖。
- 新增 `scripts/apply_financial_source_policy.py`，用于把不合格财务数值从模型字段移除。
- 清洗了 20 行 A 股不合格季度财务数据、291 行美股不合格季度财务数据，以及 39 条无 `source_url` 的美股 outlook 数值。
- 已按官方公告补回 NVDA、AVGO 的合规 actual 财务数据，并补入官方 revenue guidance；没有官方净利率 guidance 的 forecast 继续留空。
- AVGO 的 Q2 FY2026 Adjusted EBITDA guidance 已作为单独盈利能力指引展示，不参与 `gm_estimate` / `nm_estimate`。
- 已按官方公告/IR/SEC 补回 MSFT、GOOGL、META、AMZN 的 5 季合规 actual 财务数据。
- META、AMZN 的下一季 revenue guidance 已用官方区间中点展示；AMZN 的 operating income guidance 单独作为盈利能力指引展示。
- 已补回 AMD、INTC、MU 的 5 季合规 actual 财务数据，并补入官方下一季 guidance；non-GAAP/GAAP EPS 等盈利能力指标单独展示。
- 新增并增强 `scripts/fill_us_actuals_from_sec.py`，从 SEC Companyfacts 批量补齐美国公司缺失 actual；支持 `GrossProfit`、`Revenue - CostOfRevenue`、Q4 全年减前三季，以及无毛利行业的 operating income 单独盈利能力口径。
- 本轮 SEC 批量补入 203 条 actual 行。
- 修正 ASE Technology ticker 映射：页面展示 `ASE`，行情/K 线/外链使用真实 NYSE ADR ticker `ASX`。
- 美股量化 Top 5 在合规财务数据不足时不生成；当前 61 家有季度财务的美股公司均已具备完整 5 季合规 GM/NM actual 财务数据。
- 历史 `quarters` 只保留 actual/NA；forecast 统一放在 `q2_outlook`，避免图表重复显示同一预测季度。
- 已按官方 IR/公告补回 TSM、ASML、ARM、CCJ 的 5 季 actual；非美元报表已换算为美元展示，并在 `note` 保留原币值和汇率口径。
- SEC 批量补数脚本已支持“年度 official value 减其它季度 official values”派生缺失季度，并在 `note` 中标明派生口径；最近两轮又补回 18 条 actual。
- 已全量复查美股 forecast。当前 37 只有下一季官方 guidance/official outlook，24 只只有全年/年度/运营口径 guidance/consensus，0 只未找到合规公司 guidance。
- 新增 `scripts/fill_us_cash_flow_from_sec.py`，从 SEC Companyfacts 批量补充美股 `quality_metrics`：OCF、CapEx、FCF、cash、debt、net cash，并保留 CIK、XBRL tag、source URL。
- `quality_metrics` 支持 IFRS/外币披露公司；TWD/EUR/CAD 等统一换算成美元，汇率来源写入 `fx_source`。GLW 因 SEC XBRL 缺少标准 capex payment tag，按公司 2025 Form 10-K / FY2025 results release 手工录入 OCF、CapEx、FCF，保留 source URL。
- 当前美股 61 家非 ETF 公司全部已有 `free_cash_flow_billion`；5 个 ETF 无公司财务数据，仍按 ETF 不参与量化排名处理。
- 页面量化模型更新为：主题护城河 22% / 增长可见度 20% / 盈利质量 20% / 规模现金流 18% / 周期资金风险 20%。市值与 FCF 进入“规模现金流”，存储/光模块/半导体设备等高周期链条进入周期惩罚；hyperscaler CapEx/OCF 压力会传导给上游硬件链。

## 清洗后总览

| 范围 | 公司数 | 季度财务行 | 审计问题 |
|---|---:|---:|---:|
| A 股 | 28 | 140 | 0 |
| 美股 | 66 | 306 | 5 warn |
| A 股 K 线 | 28 | - | 0 |
| 美股 K 线 | 61 | - | 0 |

当前剩余问题：

| 类型 | 数量 | 说明 |
|---|---:|---|
| `no_quarters` | 5 | ETF/watch-only 标的没有季度财务数据，不参与财务模型即可 |
| `kline_failed_symbol` | 0 | 美股保存状态已更新为 `ok (61/61)` |

## 财务数据状态

### A 股

按当前审计规则，A 股已经没有 source 错误。

注意：所有 note 中明确写有估算、反推、推算等口径的季度值已被移除，不再参与模型。

### 美股

此前发现的问题：

- 231 条季度财务数据缺少 `source_url`
- 56 条 actual 财务数据用了 StockAnalysis 等二手站作为最终来源
- 1 条 forecast 没有 source

当前处理：

- 上述不合格数值已从 `rev/gm/nm` 移除
- 对应行标记为 `src: "NA"`
- `note` 写明“未找到符合规范的真实公告/guidance/consensus 来源；原财务数值已移除，不参与模型”

保留的合规财务数据：

- ASE Technology 2025Q1 至 2026Q1
- 来源为 ASE 官方 PRNewswire 财报公告
- 每个季度都有 `source_url`，并在 `note` 写明 NT$ 原始数据和换算口径
- NVIDIA 2025Q1 至 2026Q2 actual，以及 2026Q3 revenue/gross margin guidance
- Broadcom 2025Q1 至 2026Q1 actual，以及 2026Q2 revenue guidance
- Microsoft 2025Q1 至 2026Q1
- Alphabet 2025Q1 至 2026Q1
- Meta Platforms 2025Q1 至 2026Q1，以及 2026Q2 revenue guidance
- Amazon 2025Q1 至 2026Q1，以及 2026Q2 revenue/operating income guidance
- AMD 2025Q1 至 2026Q1，以及 2026Q2 revenue / non-GAAP gross margin guidance
- Intel 2025Q1 至 2026Q1，以及 2026Q2 revenue / EPS guidance
- Micron 2025Q1 至 2026Q1，以及 2026Q2 revenue / gross margin / EPS guidance
- Hubbell 2025Q1 至 2026Q1
- Rocket Lab 2025Q1 至 2026Q1
- TSMC 2025Q1 至 2026Q1，以及 2026Q2 revenue/gross margin guidance
- ASML 2025Q1 至 2026Q1，以及 2026Q2 revenue/gross margin guidance；欧元报表已换算为美元
- Arm Holdings 2025Q1 至 2026Q1；缺少直接季度披露的 Jan-Mar 季度按 SEC 年报减前三季 6-K official values 得出，并在 note 标明
- Cameco 2025Q1 至 2026Q1；加元报表已换算为美元

### 美股 Forecast 覆盖

当前有下一季官方 forecast 的 37 只：

NVDA、AVGO、AMD、INTC、QCOM、MRVL、APP、TSM、ASML、AMAT、KLAC、ONTO、SNPS、MU、SNDK、COHR、LITE、FN、MSFT、AMZN、META、AAPL、CRWV、LRCX、AMKR、TER、ANET、CRDO、ALAB、CIEN、CSCO、MPWR、GLW、PLTR、NOW、CRM、RKLB。

当前只有全年/年度/运营口径 guidance/consensus 的 24 只，会在财务图下方单独显示“全年指引”，不会画进下一季收入图：

GOOGL、TSLA、CEG、VRT、ETN、GEV、CCJ、ARM、CDNS、ASE、PWR、EME、FIX、MOD、TT、JCI、HUBB、POWL、VST、NRG、KMI、WMB、ORCL、IREN。

当前未找到合规公司 guidance 的 0 只：

无。

全年 guidance 没有被强行补进图表，是为了避免把全年目标或业务指标误画成下一季 revenue forecast。

## 模型影响

清洗后：

- A 股仍有 16 只公司具备完整 5 季合规财务数据，可继续跑模型。
- 美股目前有 61 只公司具备完整 5 季合规 GM/NM actual 财务数据：NVDA、AVGO、AMD、INTC、QCOM、MRVL、APP、TSM、ASML、AMAT、KLAC、ONTO、SNPS、MU、SNDK、COHR、LITE、FN、MSFT、GOOGL、AMZN、META、AAPL、TSLA、CRWV、CEG、VRT、ETN、GEV、CCJ、ARM、LRCX、ASE、AMKR、TER、ANET、CRDO、ALAB、CIEN、CSCO、MPWR、GLW、PWR、EME、FIX、MOD、TT、JCI、HUBB、POWL、VST、NRG、KMI、WMB、ORCL、IREN、PLTR、NOW、CRM、RKLB。
- operating income 已不再作为历史 actual 毛利率替代口径；若未来展示盈利能力指引，仅作为 forecast/guidance 补充项单独显示。
- 美股 Top 5 已有足够样本恢复生成，股票候选池已无部分缺失项。

当前美股剩余缺口：

- 股票层面已无部分缺失项。
- 5 个 ETF/watch-only 标的无公司季度财报，不参与财务模型。

这是有意行为。没有 source 的数字不能继续影响排名。

## K 线状态

### 已保存状态

- A 股：`ok (28/28)`
- 美股：`ok (61/61)`

### 已修正代码

- 页面 K 线：`ASE -> ASX`
- 页面美股行情：`ASE -> ASX`
- Yahoo 外链：`ASE -> ASX`
- GitHub 扫描脚本：`ASE -> ASX`

### 验证结果

保存状态里的 `failed: ASE` 已清除；当前审计显示美股 K 线为 `ok (61/61)`。

## 下一步

1. 按持仓/候选池优先级补美股公司公告 source。
2. 每补完一家公司，跑 `python3 scripts/audit_data_quality.py`。
3. 只有审计没有 error 且足够多公司具备完整 5 季数据时，恢复美股量化 Top 5。

## 执行命令

```bash
python3 scripts/audit_data_quality.py
```

```bash
python3 scripts/apply_financial_source_policy.py
```

## 2026-07-12 修复记录

本轮全面 review 后修复（详见 git 提交与 MODEL_FACTOR_SCORES.md 重新生成结果）：

- **quality_metrics 陈旧数据根修**：`fill_us_cash_flow_from_sec.py` 此前在 10-K 多个对比财年中选中最旧一年（NVDA 存的是 FY2024、MSFT/AAPL/GOOGL/META/AMZN 是 FY2023、部分债务残留到 2012-2014 年）。现改为按 period end 选取 + 财年 duration 校验 + 债务/现金 15 个月时效守卫 + CapEx 与 OCF 同财年配对。已全量重跑：61 家非 ETF 公司 52 家 FY2025、8 家 FY2026、TSM 停在 FY2024（SEC 20-F 滞后，warn 提示）。GLW 手工录入值加 `manual_override` 保护。
- **模型修正（index.html / build_latest_quant_factors.mjs / build_model_factor_scores.mjs 三处同步）**：A股改为与美股一致的 6 因子（移除盘中价格动量）；durabilityRaw 净现金/市值 10 倍单位错误修复；增长加速度在 5 季数据下退回 QoQ 口径（消除"有 guidance 反而扣分"）；ai_execution 缺失回落中性 5 分；美股不再惩罚低换手；负 OCF 的 capex 压力从 0.2 改为 1.2；hyperscalerFundingStress 阈值 0.45→0.25（当前值 0.37，修复前恒为 0）。
- **审计规则增强**：NA 行必须置空、F 不得留在已过去 120 天以上的季度、quality_metrics 时效与 FCF 算术校验、二手来源黑名单大幅扩充；`apply_financial_source_policy.py` 的 quarters/outlook key 分离 + 审计过期防护。本轮按新规则清洗了 5 条"东方财富摘要反推"的 A 股 2025Q1 行（000977/002156/002028/002335/002518），这 5 家暂退出量化池直到补上合规来源。
- **告警链路修复**：sender 对旧 schema 崩溃已修、buy-fresh 不再被丢弃、workflow paths 补上美股 state、新增 `scan-signals.yml` 每周五 cron 用真实 K 线扫描并直接推送；`run_us_alerts*.py`（估算价快照）退役至 scripts/deprecated/。
- **宏观层新增**：scan_signals.py 输出指数距 52 周高点回撤、观察列表空头宽度，并在大盘跌破周线 EMA21 或宽度 ≥60% 时把买点硬性降级为 buy-gated（仅观察）。
- **凭证**：run_monitor.py 中硬编码的 Gmail 应用密码与 ServerChan key 已移除改环境变量。⚠️ 旧凭证仍在 git 历史中，必须尽快吊销轮换。
- **YoY 统一修复**：run_monitor.py（此前用 Q4/Q1 的 3 季增速冒充 YoY 且忽略最新季）、scan_signals.py 与 backtest_quick.py（qs[0] 在 6 季数据下虚增 NVDA YoY 107.7%→真实 85.2%）。
- **回测修正**：凑不齐 5 只时卖出破位持仓转现金（此前在全市场回撤时满仓扛跌）、每边 20bp 成本、同期指数基准对照、幸存者偏差警示。
