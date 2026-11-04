# -*- coding: utf-8 -*-
"""
D13 数据层(二)：清洗 + 统一存储
把 data/raw/*.csv（397只散装文件）合成为一个长表 panel.parquet：
  1) 去重        —— 拉取重试可能写入重复日期，保留最后一条
  2) 价格合法化  —— 剔除 open/high/low/close <= 0 的脏行
  3) 对齐日历    —— 只保留交易日历上的日期
  4) 停牌标记    —— 在个股上市区间内、日历上存在但无数据 → is_suspended=True
  5) 异常标记    —— 单日|涨跌幅|>21%（主板限10%、创业板限20%），只标不删，留给人工审
产出：data/panel.parquet + data/quality_report.csv
"""
import os, glob
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data")
START, END = "2020-01-01", "2025-10-31"

# ---- 交易日历 ----
cal = pd.read_csv(os.path.join(OUT, "交易日历.csv"), encoding="gbk")
cal["trade_date"] = pd.to_datetime(cal["trade_date"])
cal_dates = pd.DatetimeIndex(
    cal.loc[(cal.trade_date >= START) & (cal.trade_date <= END), "trade_date"].sort_values()
)

frames, rows_stat = [], []
for fp in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
    df = pd.read_csv(fp, parse_dates=["date"])
    if len(df) == 0:
        continue
    if "code" not in df.columns:   # index_*.csv 是基准指数文件，列结构不同，跳过
        continue
    df = df.sort_values("date")
    code = df["code"].iloc[0]
    # 1) 去重
    n_dup = int(df.duplicated("date", keep="last").sum())
    df = df.drop_duplicates("date", keep="last")
    # 2) 价格合法化
    n_bad = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    # 3) 对齐日历（丢弃非交易日行）
    n_offcal = len(df) - int(df["date"].isin(cal_dates).sum())
    df = df[df["date"].isin(cal_dates)].copy()
    if len(df) == 0:
        continue
    # 5) 异常收益标记（按该股自身相邻交易日比）
    df["abnormal_ret"] = df["close"].pct_change().abs() > 0.21
    n_abn = int(df["abnormal_ret"].sum())
    frames.append(df)
    rows_stat.append(dict(code=code, name=df["name"].iloc[0], group=df["group"].iloc[0],
                          rows=len(df), dup_removed=n_dup, bad_removed=n_bad,
                          offcal_removed=n_offcal, abnormal_days=n_abn))

panel = pd.concat(frames, ignore_index=True)

# ---- 4) 停牌标记：宽表矩阵上算"上市区间内但缺数据" ----
close_w = panel.pivot(index="date", columns="code", values="close").reindex(cal_dates)
listed = close_w.notna().to_numpy()
pos = np.arange(len(cal_dates))[:, None]
first_pos = np.argmax(listed, axis=0)            # 每列第一个有数据的位置
last_pos  = close_w.shape[0] - 1 - np.argmax(listed[::-1], axis=0)
in_range = (pos >= first_pos[None, :]) & (pos <= last_pos[None, :])
suspend_mask = in_range & ~listed                # 区间内无数据=停牌

# 把停牌标记回填到长表：(date, code) 命中 suspend_mask 即 is_suspended
sus_pairs = set(zip(close_w.index[np.where(suspend_mask)[0]],
                    close_w.columns[np.where(suspend_mask)[1]]))
panel["is_suspended"] = panel.set_index(["date", "code"]).index.isin(sus_pairs)

# ---- 落地 ----
panel = panel.sort_values(["code", "date"]).reset_index(drop=True)
panel.to_parquet(os.path.join(OUT, "panel.parquet"), index=False, compression="snappy")
stat = pd.DataFrame(rows_stat)
stat["suspend_days"] = stat["code"].map(panel.groupby("code")["is_suspended"].sum())
stat.to_csv(os.path.join(OUT, "quality_report.csv"), index=False, encoding="utf-8-sig")

print(f"面板: {len(panel)}行 × 股票{panel.code.nunique()}只 × 日历{len(cal_dates)}天")
print(f"去重共删{stat.dup_removed.sum()} | 坏价删{stat.bad_removed.sum()} | 非交易日删{stat.offcal_removed.sum()}")
print(f"停牌行标记: {int(panel.is_suspended.sum())} | 异常收益行: {int(panel.abnormal_ret.sum())}")
print("异常最多的5只:")
print(stat.sort_values("abnormal_days", ascending=False).head(5).to_string(index=False))
