# -*- coding: utf-8 -*-
"""
D5 作业：成本敏感性测试（本地版）
用你自己 D3 设计的规则（收盘>昨ma5买、<昨ma5卖）跑茅台真实数据，
对比三档佣金下的收益差距 —— 亲眼看看手续费怎么吃掉利润。
运行：python d5_cost_sensitivity.py
"""
import pandas as pd
import numpy as np

import os
df = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "maotai.csv"))

# ---- 你D3写的信号（shift(1)防前视的老朋友）----
df["ma5"] = df["收盘"].rolling(5).mean()
df["ma5_signal"] = df["ma5"].shift(1)
df["ret"] = df["收盘"].pct_change()

# 持仓状态：1=持有（今天收盘>昨天均线），0=空仓
df["hold"] = (df["收盘"] > df["ma5_signal"]).astype(int)
df["hold"] = df["hold"].fillna(0)

# 换仓日 = 今天持仓状态和昨天不一样（发生了一次买或卖）
df["trade"] = df["hold"].diff().abs().fillna(0)   # 1=换仓, 2=当天买卖各一次(不会发生)
n_trades = int(df["trade"].sum())

print(f"回测天数: {len(df)}")
print(f"换仓次数(单边算一次): {n_trades}")
print(f"信号持仓天数占比: {df['hold'].mean():.1%}")
print()

# ---- 策略收益：持有日的日收益归策略，空仓日收益为0 ----
# 每换一次仓交一次佣金(买卖各交一次，一次换仓=一买一卖=2次佣金)
# 卖出还要交印花税万五
def run(cost_rate, label):
    """cost_rate: 单边佣金率; 印花税固定万五只在卖出收"""
    # ★ 防前视：hold[i]是"i日收盘后"才知道的信号，只能赚 i+1日的收益
    #   所以持仓状态要 shift(1) 再和收益相乘（D2学的同一个坑，我犯了）
    daily = df["ret"] * df["hold"].shift(1)
    # 交易成本：换仓日本身就是"买入日"或"卖出日"
    # 简化：每次换仓收 佣金 + (卖出时)印花税 ≈ 每次换仓 2*佣金 + 万五
    cost_per_trade = 2 * cost_rate + 0.0005
    total_cost = n_trades * cost_per_trade
    gross = (1 + daily.fillna(0)).prod() - 1          # 不含成本的策略收益
    net = gross - total_cost                          # 扣完成本
    print(f"{label:14s} 佣金{cost_rate:.2%} | 毛收益 {gross:+.2%} | "
          f"成本 {total_cost:.2%} | 净收益 {net:+.2%}")
    return net

run(0.00000, "理想(零成本)")
run(0.00030, "万三(现实)")
run(0.00100, "千一(高成本)")

# ---- 对照：买入持有不动 ----
bh = (1 + df["ret"].fillna(0)).prod() - 1
print(f"\n买入持有茅台两年半: {bh:+.2%}（一次买一次卖，成本仅万三+万五≈0.11%）")
