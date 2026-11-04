# -*- coding: utf-8 -*-
"""
D14 数据质量校验：validate_data.py
跑一次自动报出所有异常，不靠肉眼翻。
四项检查（对应计划D14清单）：
  [1] 交易日对齐：数据里出现非交易日？每票首末行是否落在日历上？
  [2] 缺失统计：上市区间内缺多少日历日（停牌/缺数）；关键列NaN数
  [3] 极值/逻辑检测：|日涨跌|>21%；OHLC自相矛盾(最高<最低等)；零/负价残留
  [4] 重复行：(code, date) 重复
输出：控制台摘要 + data/validation_report.csv（逐票明细，供人工只看异常票）
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
panel = pd.read_parquet(os.path.join(ROOT, "data", "panel.parquet"))
cal = pd.read_csv(os.path.join(ROOT, "data", "交易日历.csv"), encoding="gbk")
cal["trade_date"] = pd.to_datetime(cal["trade_date"])
START, END = panel["date"].min(), panel["date"].max()
cal_dates = pd.DatetimeIndex(cal.loc[(cal.trade_date >= START) & (cal.trade_date <= END),
                                      "trade_date"].sort_values())

print(f"面板: {len(panel)}行 × {panel.code.nunique()}只 | 日历窗口 {len(cal_dates)}天\n")

# ---------- [4] 重复行 ----------
dup = panel.duplicated(["code", "date"], keep=False)
print(f"[4] 重复(code,date)行: {int(dup.sum())}")

# ---------- [1] 交易日对齐 ----------
off_cal = ~panel["date"].isin(cal_dates)
print(f"[1] 非交易日行: {int(off_cal.sum())}")
bad_cal_codes = panel.loc[off_cal, "code"].unique()[:5]
if len(bad_cal_codes):
    print("    涉及:", list(bad_cal_codes))

# ---------- [2]+[3] 逐票检查 ----------
rows = []
for code, g in panel.groupby("code"):
    g = g.sort_values("date")
    ret = g["close"].pct_change()
    # 极值
    n_abn = int((ret.abs() > 0.21).sum())
    max_ret = float(ret.abs().max())
    # OHLC逻辑: high应为四价最大, low应为四价最小
    bad_hl = int(((g["high"] < g["low"]) |
                  (g["high"] < g[["open", "close"]].max(axis=1)) |
                  (g["low"]  > g[["open", "close"]].min(axis=1))).sum())
    # 缺失：首末行之间的日历日应有而未有
    span = cal_dates[(cal_dates >= g["date"].min()) & (cal_dates <= g["date"].max())]
    missing = int(len(span) - g["date"].isin(span).sum())
    nan_cols = int(g[["open", "high", "low", "close"]].isna().sum().sum())
    rows.append(dict(code=code, name=g["name"].iloc[0], group=g["group"].iloc[0],
                     rows=len(g), span_days=len(span), missing_days=missing,
                     nan_prices=nan_cols, abnormal_days=n_abn,
                     max_abs_ret=round(max_ret, 4), ohlc_broken=bad_hl))

rep = pd.DataFrame(rows)
rep.to_csv(os.path.join(ROOT, "data", "validation_report.csv"),
           index=False, encoding="utf-8-sig")

n_bad = int(((rep.missing_days > 0) | (rep.abnormal_days > 0) |
             (rep.ohlc_broken > 0) | (rep.nan_prices > 0)).sum())
print(f"[2] 缺失日合计: {rep.missing_days.sum()} 天 | 含缺失的票: {(rep.missing_days>0).sum()}只")
print(f"    价格NaN: {rep.nan_prices.sum()} 个")
print(f"[3] OHLC自相矛盾行: {rep.ohlc_broken.sum()} | 异常收益日合计: {rep.abnormal_days.sum()}")
print(f"\n>>> 完全干净的票: {len(rep)-n_bad}/{len(rep)} | 有任一项异常的票: {n_bad}")
print("\n缺失日最多的5只（长期停牌/中途退市属正常，但要知道是多少）:")
print(rep.sort_values("missing_days", ascending=False).head(5)
        [["code","name","group","missing_days","abnormal_days","max_abs_ret"]].to_string(index=False))
print("\n单日最大涨跌幅TOP5（应全是退市整理期/科创创业板20%线附近）:")
print(rep.sort_values("max_abs_ret", ascending=False).head(5)
        [["code","name","group","max_abs_ret","abnormal_days"]].to_string(index=False))
