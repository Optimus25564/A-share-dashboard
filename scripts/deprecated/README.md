# Deprecated

`run_us_alerts.py` / `run_us_alerts_v2.py` 已退役 (2026-07-12)：

- 两者使用手工估算的价格/EMA（v2 全部硬编码 2026-06-05 快照），且 `today` 被冻结，不能作为监控。
- 替代方案：`.github/scripts/scan_signals.py`（真实腾讯 K 线）由 `.github/workflows/scan-signals.yml` 每周五定时运行，扫描后直接推送。

保留仅作历史参考，不要再运行。
