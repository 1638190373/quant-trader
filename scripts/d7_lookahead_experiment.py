# -*- coding: utf-8 -*-
"""
D7 作业：前视偏差对照实验（故意做坏 vs 修正）

规则（D3你自己设计的）：收盘价 > 昨日5日均线 → 持有；否则空仓

  版本A【故意含前视偏差】：hold[i] 用的是"截至 i 日收盘"的均线判断
      —— i 日的收益还没落袋你就已经"预知"了 i 日收盘，等于偷看答案
  版本B【修正版】：hold 整体 shift(1)
      —— 昨天收盘做完判断，今天才知道的结果归我

逐项自查清单（计划D7原文，对照聚宽v2策略）：
  [1] 所有信号是否shift？            v2: attribute_history只给截至昨天的日线 ✓
  [2] end_date是否包含当天？          v2: 14:55用last_price实时价（当下可得）✓
  [3] 是否用当日收盘价当日成交？      v2: 信号与成交同一时点14:55，但信号只用
                                      昨日及以前数据+当下实时价，不偷未来 ✓
  [4] 是否用了全样本统计量？          v2: 无——窗口固定20天滚动，不用全期均值 ✓
      （反例：若用"全期442天均价"判断今天买不买，就是第4类前视——
        今天的决策用到了明天的数据）
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# 找数据（桌面或项目data目录都能跑）
for p in ["maotai.csv", "../data/maotai.csv",
          os.path.expanduser("~/Desktop/maotai.csv"),
          r"D:/Documents/qwen-agent/OtbNL0L3By/default/quant-trader/data/maotai.csv"]:
    if os.path.exists(p):
        df = pd.read_csv(p)
        break
df = df.sort_values("日期").reset_index(drop=True)
df["日期"] = pd.to_datetime(df["日期"])

N = len(df)
YEARS = N / 252.0   # 442个交易日 ≈ 1.75年

df["ma5"]  = df["收盘"].rolling(5).mean()
df["ret"]  = df["收盘"].pct_change()
df["hold"] = (df["收盘"] > df["ma5"].shift(1)).astype(float)  # 判断本身合法（用昨日均线）

# ============ 版本A：故意含前视偏差 ============
# 错误点：ret[i]（今天涨跌）× hold[i]（收盘后才知道的信号）→ 预知今天
equity_a = (1 + df["ret"].fillna(0) * df["hold"]).cumprod()

# ============ 版本B：修正版 ============
# 正确：昨天的判断，决定今天的持仓
equity_b = (1 + df["ret"].fillna(0) * df["hold"].shift(1).fillna(0)).cumprod()

def annualized(e):
    return e.iloc[-1] ** (1 / YEARS) - 1

print(f"数据: 贵州茅台 {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}（{N}个交易日 ≈ {YEARS:.2f}年）")
print()
print("            总收益        年化收益")
print(f"版本A 前视版:  {equity_a.iloc[-1]-1:+9.2%}   {annualized(equity_a):+8.2%}")
print(f"版本B 修正版:  {equity_b.iloc[-1]-1:+9.2%}   {annualized(equity_b):+8.2%}")
print(f"{'─'*46}")
print(f"★ 前视偏差让年化虚高了 {(annualized(equity_a)-annualized(equity_b))*100:.1f} 个百分点"
      f"（零成本、同一规则，只改了持仓错位一格）")
print(f"★ 修正版真实成绩跑输买入持有："
      f"{(1+df['ret'].fillna(0)).prod()-1:+.2%}")

# ============ 画图 ============
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(df["日期"], equity_a * 100000, color="#e06666", lw=2,
        label=f"版本A 含前视偏差（虚高）: {equity_a.iloc[-1]-1:+.1%}")
ax.plot(df["日期"], equity_b * 100000, color="#38b000", lw=2,
        label=f"版本B 修正版（真实）: {equity_b.iloc[-1]-1:+.1%}")
ax.plot(df["日期"], (df["收盘"]/df["收盘"].iloc[0]) * 100000, color="#999999",
        lw=1.2, ls="--", label="买入持有")
ax.set_title("同一个策略，一个 shift(1) 的差距（10万本金）")
ax.set_ylabel("账户市值（元）")
ax.legend()
ax.grid(alpha=0.3)
# 日期标签太密会糊成黑条：每2个月只画一个刻度，并转成日期类型
import matplotlib.dates as mdates
df["日期"] = pd.to_datetime(df["日期"])
ax.set_xticks(df["日期"][::40])
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
fig.autofmt_xdate()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "d7_lookahead.png") \
      if "Desktop" not in os.path.dirname(os.path.abspath(__file__)) \
      else "d7_lookahead.png"
plt.savefig(out, dpi=120)
print(f"\n曲线图已保存: {out}")
