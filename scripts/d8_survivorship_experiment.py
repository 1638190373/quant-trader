# -*- coding: utf-8 -*-
"""
D8 作业：幸存者偏差对照实验（本地版）

问题：AI/新手最常见的作弊——"用今天的股票名单，回测过去5年"。
今天还活着的票=被筛选过的赢家；退市的票(乐视/暴风/康得新/华业)永远
进不了你的池子，回测替你把它们"提前剔除"了，收益必然虚高。

实验设计（近似"各时点成分股池"，诚实标注局限）：
  池A【幸存者池】= 当前沪深300里抽12只行业龙头（2019年就在、活到今天）
  池B【真实池】  = 池A + 4只2019年同样在A股正常交易、后来退市的票
  2019年初等权买入，退市票按最后交易日清算转现金，持有到2025-10-31
  分别用 ①买入持有 ②D3均线规则(收盘>昨5日线持有) 跑两个池，对比收益

数据：akshare新浪接口；存活票前复权，退市票不复权(本来就要归零，用真实价)
局限：4只退市票是演示样本，非2019年全市场；偏差方向与量级可信，
      精确值需在聚宽用 get_index_stocks(历史日期)+get_all_securities 重做
"""
import os, time, json
import pandas as pd
import numpy as np
import akshare as ak
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

SURVIVORS = {  # 池A：今天的沪深300成员（12只跨行业）
    "sh600519": "贵州茅台", "sh601318": "中国平安", "sz000858": "五粮液",
    "sh600036": "招商银行", "sz002415": "海康威视", "sz300750": "宁德时代",
    "sh601899": "紫金矿业", "sz000333": "美的集团", "sh600900": "长江电力",
    "sh601012": "隆基绿能", "sz000651": "格力电器", "sh600309": "万华化学",
}
DEAD = {       # 池B追加：2019年就在交易、后来退市的4只
    "sz300104": "乐视网",    # 2020-07 退市
    "sz300431": "暴风集团",  # 2020-11 退市
    "sz002450": "康得新",    # 2021-05 退市(财务造假122亿)
    "sh600240": "华业资本",  # 2020-07 退市
}

def load_one(sym, adjust):
    cache = os.path.join(DATA_DIR, f"d8_{sym}.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache, parse_dates=["date"])
    for i in range(3):
        try:
            d = ak.stock_zh_a_daily(symbol=sym, start_date="20190101",
                                    end_date="20251031", adjust=adjust)
            d = d.reset_index()[["date", "close"]].rename(columns={"close": sym})
            d["date"] = pd.to_datetime(d["date"])
            d.to_csv(cache, index=False)
            time.sleep(0.8)
            return d
        except Exception as e:
            print(f"  {sym} 第{i+1}次失败: {type(e).__name__}")
            time.sleep(2)
    return None

def build_panel(symbols, adjust):
    """把多只票的收盘价对齐成一张表（行=交易日，列=股票代码）"""
    panel = None
    for sym in symbols:
        d = load_one(sym, adjust)
        if d is None:
            print(f"  ⚠️ {sym} 拉取失败，跳过")
            continue
        panel = d if panel is None else panel.merge(d, on="date", how="outer")
        time.sleep(0.8)
    return panel.sort_values("date").set_index("date")

print("== 拉取数据（首次约1分钟，之后走缓存）==")
px_live = build_panel(list(SURVIVORS), "qfq")     # 存活票：前复权
px_dead = build_panel(list(DEAD), "")             # 退市票：不复权真实价
panel_a = px_live                                 # 池A：幸存者
panel_b = pd.concat([px_live, px_dead], axis=1)   # 池B：真实池

# 退市票退市后 → 最后收盘价凝固成现金（ffill），这正是真实投资者拿到的残值
def portfolio(px, weights_equal=True):
    norm = px / px.iloc[0]
    return norm.ffill().mean(axis=1)   # 等权组合净值

nv_a_bh, nv_b_bh = portfolio(panel_a), portfolio(panel_b)

# 均线策略版：每只票独立跑 D3 规则，等权
def strategy_nv(px):
    px = px.where(px > 0)                            # 防御: 接口偶发0价当NaN
    ma = px.rolling(5).mean().shift(1)               # 昨日均线（防前视）
    hold = (px > ma).astype(float)                   # i日收盘后的持仓判断
    hold = hold.where(px.notna(), 0.0)               # 退市后该票不再持仓
    daily_ret = px.pct_change().where(px.notna(), 0.0).fillna(0)
    # ★ 第三次踩同一个坑的修正：ret[i]×hold[i] 是前视（收盘才知道的判断
    #   不能赚当天的钱），必须 hold.shift(1) —— 昨天决定，今天持有
    port_ret = (daily_ret * hold.shift(1).fillna(0)).mean(axis=1)
    return (1 + port_ret).cumprod()                  # 组合日收益累乘成净值

nv_a_st, nv_b_st = strategy_nv(panel_a), strategy_nv(panel_b)

def ann(nv):
    years = (nv.index[-1] - nv.index[0]).days / 365.25
    return nv.iloc[-1] ** (1 / years) - 1

print(f"\n数据区间: {nv_a_bh.index[0].date()} ~ {nv_a_bh.index[-1].date()}"
      f"（{len(nv_a_bh)}个交易日 ≈ 6.8年）")
print(f"\n{'':12s}{'池A幸存者(12只)':>18s}{'池B真实(16只)':>16s}{'偏差':>12s}")
for name, a, b in [("买入持有", nv_a_bh, nv_b_bh), ("均线策略", nv_a_st, nv_b_st)]:
    print(f"{name:12s}{a.iloc[-1]-1:>+17.1%}{b.iloc[-1]-1:>+15.1%}"
          f"{a.iloc[-1]-b.iloc[-1]:>+11.1%}")
print(f"{'年化偏差(持有)':12s}{ann(nv_a_bh)-ann(nv_b_bh):>+17.1%}")

# 逐票成绩单（退市票的惨状一目了然）
print("\n== 各票全程涨跌幅（持有到最后）==")
last = panel_b.ffill().iloc[-1] / panel_b.iloc[0] - 1   # 比率-1 = 真实涨跌幅
dead_rows = {k: f"{DEAD[k]} {last[k]:+.0%}" for k in DEAD}
print("  退市组: " + " | ".join(dead_rows.values()))

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.plot(nv_a_bh.index, nv_a_bh, color="#e06666", lw=2,
        label=f"池A 幸存者名单·买入持有 {nv_a_bh.iloc[-1]-1:+.0%}")
ax.plot(nv_b_bh.index, nv_b_bh, color="#8b0000", lw=2, ls="--",
        label=f"池B 真实名单·买入持有 {nv_b_bh.iloc[-1]-1:+.0%}")
ax.plot(nv_a_st.index, nv_a_st, color="#38b000", lw=2,
        label=f"池A 幸存者名单·均线策略 {nv_a_st.iloc[-1]-1:+.0%}")
ax.plot(nv_b_st.index, nv_b_st, color="#1e6b1e", lw=2, ls="--",
        label=f"池B 真实名单·均线策略 {nv_b_st.iloc[-1]-1:+.0%}")
ax.set_title(f"幸存者偏差：10万本金，{'用今天的名单' } vs {'含已退市票'}")
ax.set_ylabel("账户市值（元）")
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
ax.set_xticks(nv_a_bh.index[::80])
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
fig.autofmt_xdate()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "d8_survivorship.png")
plt.savefig(out, dpi=120)
print(f"\n图已保存: {out}")
