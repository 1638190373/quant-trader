# 股票量化交易系统

> 45天量化程序员入职准备项目

## 一句话简介
从零搭建 A 股量化回测与交易系统，涵盖数据获取、回测引擎、风控、绩效分析、每日运维监控。

## 目录说明

| 目录 | 用途 |
|------|------|
| `data/` | 行情数据存储（本地 Parquet / SQLite） |
| `strategy/` | 策略实现（继承 Strategy 基类） |
| `backtest/` | 回测引擎（逐 Bar 撮合、成本模型） |
| `risk/` | 风控模块（仓位、止损、熔断） |
| `report/` | 绩效报告与可视化 |
| `scripts/` | 定时任务、数据校验、日报生成 |
| `config/` | 配置文件（参数、策略设置） |

## 数据源
- akshare（免费）
- tushare（备选）

## 一键运行

```bash
git clone <repo-url>
cd quant-trader
pip install -r requirements.txt
python scripts/run_demo.py
```

## 免责声明

本项目仅用于学习和面试展示，不构成任何投资建议。历史回测收益不代表未来表现。

## 开发日志

见 [日志.md](日志.md)