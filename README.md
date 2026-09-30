# A-share Dashboard · 国产算力主线

A股关注列表 + 模拟交易仪表盘，聚焦"国产算力 / 去英伟达化"主线。

**在线访问：** https://optimus25564.github.io/A-share-dashboard/

## 功能

- 📊 **关注列表** — 17只主线 A股，分 4 层（核心芯片 / 服务器整机 / 上游支撑 / 物理层）
- 📈 **行情数据** — 富途 OpenAPI REST；私有 GitHub Actions 后端刷新，公开网页不保存令牌
- 💹 **模拟交易** — A股 300 万人民币 / 美股 $300,000 两个独立账户，支持"按策略一键建仓"（6 因子 Top10 + 宏观阶梯），买卖、持仓、盈亏曲线、CSV 导出，数据存 localStorage
- 🕯 **K线 + 指标** — 180 日前复权 K线，含 MA / MACD / RSI / KDJ / BOLL 指标
- 🧭 **策略备忘** — 2026 关键催化剂时间轴 + "算力 ⇌ 电力"交叉观察

## 使用

直接打开 [GitHub Pages 链接](https://optimus25564.github.io/A-share-dashboard/) 即可。模拟交易数据是浏览器本地的，每个用户独立。当前授权可读取美股快照，美股每 15 分钟刷新；A 股使用富途最新日线，K 线每日刷新。账户取得 A 股实时行情权限后，后台会自动优先使用实时快照。

## 数据规范

财务数据必须有真实公告来源，详见 [FINANCIAL_DATA_SOURCES.md](FINANCIAL_DATA_SOURCES.md)。

当前数据质量审计见 [DATA_QUALITY_AUDIT.md](DATA_QUALITY_AUDIT.md)。

## 免责声明

本项目仅作个人投资研究跟踪，**不构成任何投资建议**。行情数据来自富途 OpenAPI REST，页面显示后台最近一次成功刷新结果；模拟盘不含手续费、印花税、T+1 限制。
