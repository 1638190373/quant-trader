# -*- coding: utf-8 -*-
"""
D9 作业：过拟合自查 —— 布林带参数网格 ±20%

规则（复刻聚宽v2，本地日线近似）：
  入场: 昨收 < 昨日布林下轨 且 今收 > 今日布林下轨(用截至昨20日+今收计算)
        且 带宽/中轨 > W阈值 且 今日跌幅 > -8%
  出场: 昨收 > 昨上轨 且 今收 < 今上轨(反弹结束) | 收盘 < 成本×(1-止损) | 数据结束清仓
  成交: T日收盘后出信号，T+1开盘成交（防前视，hold逻辑同D7教训：
        今天的决策只能用截至昨天的信息+今天的收盘观察，赚明天的钱）
  成本: 佣金双边万三(各含0.1%滑点近似) + 卖出印花税万五

网格(各±20%)：
  BB_PERIOD: 20 → [16, 20, 24]
  BB_STD:   2.0 → [1.6, 2.0, 2.4]
  WIDTH:    10  → [8, 10, 12]
"""
import os
import pandas as pd
import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "maotai.csv")
df = pd.read_csv(DATA).sort_values("日期").reset_index(drop=True)
o = df["开盘"].values
c = df["收盘"].values
N = len(df)

COST_BUY = 0.0003 + 0.001    # 佣金万三+滑点0.1%
COST_SELL = 0.0003 + 0.0005 + 0.001  # 佣金+印花税+滑点

def backtest(period, k_std, width_thresh, stop_loss=0.06):
    """返回 (总收益, 交易次数, 最大回撤)"""
    closes = pd.Series(c)
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std(ddof=1)
    up, dn = mid + k_std * std, mid - k_std * std
    width = (up - dn) / mid * 100

    cash, shares, cost_basis = 1.0, 0.0, 0.0
    equity = np.empty(N)
    n_trades, i = 0, 0
    while i < N:
        # i日收盘观察到信号 → i+1日开盘成交（无未来数据）
        if i >= period + 1 and shares == 0:
            w = c[max(0,i-period+1):i+1]
            t_dn = w.mean() - k_std * w.std(ddof=1)
            bounced = (c[i-1] < dn.iloc[i-1]) and (c[i] > t_dn)
            wide = (not np.isnan(width.iloc[i-1])) and width.iloc[i-1] > width_thresh
            crash = (c[i] - c[i-1]) / c[i-1] <= -0.08
            if bounced and wide and not crash and i + 1 < N:
                px = o[i+1] * (1 + COST_BUY)
                shares, cost_basis = cash / px, px
                cash, n_trades = 0.0, n_trades + 1
        elif shares > 0:
            w = c[max(0,i-period):i]                             # 截至昨日
            y_up = w.mean() + k_std * w.std(ddof=1)
            w2 = c[max(0,i-period+1):i+1]
            t_up = w2.mean() + k_std * w2.std(ddof=1)
            exit_now = (c[i-1] > y_up and c[i] < t_up) or (c[i] < cost_basis * (1 - stop_loss))
            if exit_now and i + 1 < N:
                cash = shares * o[i+1] * (1 - COST_SELL)
                shares, n_trades = 0.0, n_trades + 1
        equity[i] = cash + shares * c[i]
        i += 1
    if shares > 0:
        cash = shares * c[-1] * (1 - COST_SELL)
    total = cash - 1.0
    peak = np.maximum.accumulate(equity)
    mdd = ((equity - peak) / peak).min()
    return total, n_trades // 2, mdd   # 买卖各算半笔→完整轮次

print("网格: BB_PERIOD[16,20,24] × BB_STD[1.6,2.0,2.4] × WIDTH[8,10,12]")
print("每格: 总收益 | 轮次 | 最大回撤   （基准格: 20/2.0/10）\n")

rows = []
for p in [16, 20, 24]:
    line = []
    for k in [1.6, 2.0, 2.4]:
        for w in [8, 10, 12]:
            r, t, m = backtest(p, k, w)
            rows.append((p, k, w, r, t, m))

res = pd.DataFrame(rows, columns=["period", "std", "width", "收益", "轮次", "回撤"])
res["rank"] = res["收益"].rank(ascending=False)

# 三维透视: period×std（width=10固定）与 period×width（std=2.0固定）
pv = res[res.width == 10].pivot(index="period", columns="std", values="收益")
print("== 收益曲面(宽度阈值=10) 行=周期 列=std ==\n", (pv * 100).round(1).to_string(), "\n")
pv2 = res[res["std"] == 2.0].pivot(index="period", columns="width", values="收益")
print("== 收益曲面(std=2.0) 行=周期 列=宽度阈值 ==\n", (pv2 * 100).round(1).to_string(), "\n")

best, worst = res.loc[res["收益"].idxmax()], res.loc[res["收益"].idxmin()]
base = res[(res.period==20)&(res["std"]==2.0)&(res.width==10)].iloc[0]
print(f"最优格: period={best.period} std={best['std']} width={best.width} → {best['收益']:+.1%} (第{int(best['rank'])}名/27)")
print(f"最差格: period={worst.period} std={worst['std']} width={worst.width} → {worst['收益']:+.1%}")
print(f"基准格(20/2.0/10): {base['收益']:+.1%}")
print(f"\n曲面统计: 均值{res['收益'].mean():+.1%} 标准差{res['收益'].std():.1%} "
      f"极差{res['收益'].max()-res['收益'].min():.1%}")
print(f"基准格排名: {int(base['rank'])}/27 —— 中心参数{'不是' if 6<=base['rank']<=21 else '是'}孤立尖峰" if 6<=base['rank']<=21 else f"基准格排名: {int(base['rank'])}/27")

n_pos = (res["收益"] > 0).sum()
print(f"\n正收益格数: {n_pos}/27 ({n_pos/27:.0%})")
print(f"平均交易轮次: {res['轮次'].mean():.1f}")
print("\n== 自由参数清点（计划要求≤3） ==")
print("信号类: BB_PERIOD=20, BB_STD=2.0, WIDTH=10 → 3个")
print("风控类: STOP_LOSS=6%, POSITION_RATIO=30%, 暴跌剔除-8% → 3个")
print("合计6个 > 3 —— 按纪律应把风控参数'钉死为行业惯例'(止损/仓位不调参)，")
print("真正参与调参的自由参数压回3个：正是本网格在做的。")
