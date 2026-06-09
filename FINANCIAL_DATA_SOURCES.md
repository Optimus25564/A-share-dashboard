# Financial Data Source Policy

本项目里的所有财务数据必须可追溯。凡是进入 `data/companies.json` 或 `data/companies_us.json` 的季度/年度财务字段，都必须有明确来源。Actual 必须来自真实公告数据；forecast 也必须来自公司 guidance、管理层公开口径或明确可追溯的市场一致预期，不能自己瞎编。

## 适用范围

以下字段都属于财务数据，必须有 source：

- `quarters[].rev`：营收
- `quarters[].gm`：毛利率
- `quarters[].nm`：净利率
- `forecast` / `guidance` / `catalysts` 中出现的营收、利润率、EPS、EBITDA、订单、backlog、capex 等数字
- `market_cap_billion`、`avg_turnover_pct` 如果用于模型打分，也要能追溯来源或计算日期

## Source 要求

优先级从高到低：

1. 公司官网 Investor Relations 公告、财报 PDF、earnings release、Form 6-K / 8-K / 10-Q / 10-K。
2. 交易所或 SEC/监管披露文件。
3. PRNewswire / BusinessWire 等公司正式发布渠道，且发布主体必须是公司本身。

不允许作为 source：

- StockAnalysis、Yahoo Finance、Seeking Alpha、新闻转述、博客、AI 摘要。
- 没有原始公告链接的截图或表格。
- 模型估算、季节性反推、同比倒推。
- 自己按趋势、季节性、同比、环比、新闻语气推出来的 forecast。

二手来源只能用于发现线索，不能作为最终财务数据来源。若使用市场一致预期，必须能追溯到明确的 consensus 数据来源和发布日期。

## 数据字段规范

每个季度对象至少应包含：

```json
{
  "q": "2025Q1",
  "rev": 45.6,
  "gm": 16.8,
  "nm": 5.1,
  "src": "A",
  "source_url": "https://...",
  "note": "Q1 2025 actual: original currency/value; conversion method if any"
}
```

字段含义：

- `src: "A"` 表示 actual，必须来自真实公告数据。
- `src: "F"` 表示 forecast，只能用于未来季度或未发布财报的当前季度，且必须来自公司 guidance、管理层公开口径或明确可追溯的 consensus，不得用于已发布财报的历史季度。
- `src: "NA"` 表示没有合规来源，`rev/gm/nm` 必须为 `null`，不得参与模型计算。
- `source_url` 必须指向公告原文、监管文件、公司 guidance 原文，或明确的 consensus 来源。
- `note` 必须写清楚原始币种、原始数值和换算方式。

## 口径要求

- 页面里的美股财务 `rev` 单位是亿美元；如果原公告是 NT$、EUR、JPY 等，必须在 `note` 写明换算汇率。
- 同一家公司同一组季度应尽量使用同一换算口径，避免季度间因为汇率选择不同制造假波动。
- `gm` 和 `nm` 优先直接取公告披露；如果需要用公告数字计算，必须在 `note` 里说明计算方式。
- 财年季度和自然季度不能混写。如果公司使用 FY quarter，`note` 必须写明财报截止日。

## 修改数据前检查清单

改任何财务数据前，先确认：

- 该季度是否已经发布正式财报。
- `src` 是否符合 actual/forecast 的含义。
- `source_url` 是否为公司公告、监管披露、公司 guidance 或明确 consensus 来源。
- 原始数据、换算数据、页面单位是否一致。
- 改动是否会影响量化排名、Top 5、候选池或策略判断。

## 当前原则

宁可缺数据，也不要填无来源的假精确数字。

如果找不到真实公告数据：

- 历史季度不要标 `A`。
- 未来季度也不要自己编 forecast；没有 guidance 或 consensus source 就留空。
- `F` 必须有 `source_url` 和 `note`，并说明是 guidance、management outlook 还是 consensus。
- 没有合规来源时使用 `src: "NA"`，并把 `rev/gm/nm` 置为 `null`。
- 该公司应从依赖完整 5 季财务数据的模型评分中排除，直到 source 补齐。
