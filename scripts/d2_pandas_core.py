"""
D2 练习：pandas 核心（最重要的一天）
=====================================
DataFrame/Series、read_csv、loc/iloc、rolling、shift、pct_change、
diff、merge、groupby、resample

练习：用日线数据算 5日/20日均线，算日收益，输出收益的均值、标准差、最大单日跌幅
"""

import pandas as pd
import numpy as np
import akshare as ak

# ============================================================
# 0. 拉取真实日线数据
# ============================================================
SYMBOL = "600519"  # 贵州茅台

df = ak.stock_zh_a_hist(symbol=SYMBOL, period="daily", start_date="20200101", end_date="20251031", adjust="qfq")
df["日期"] = pd.to_datetime(df["日期"])
df = df.sort_values("日期").reset_index(drop=True)
df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
                   "最低": "low", "成交量": "volume", "成交额": "amount"}, inplace=True)
df = df[["date", "open", "high", "low", "close", "volume", "amount"]]
print(f"数据条数: {len(df)}，日期范围: {df['date'].min().date()} ~ {df['date'].max().date()}")

# ============================================================
# 1. DataFrame / Series 基础
# ============================================================
# Series 是一列，DataFrame 是多列的表
print(f"\n收盘价列类型: {type(df['close'])}")   # Series
print(f"整个表类型:   {type(df)}")                # DataFrame

# ============================================================
# 2. loc / iloc 定位
# ============================================================
# loc：按标签（索引/条件）
# iloc：按位置（整数序号）
print("\n=== loc / iloc ===")
print(f"iloc[0]:   {df.iloc[0]['date'].date()}  收盘 {df.iloc[0]['close']}")   # 第1行
print(f"iloc[-1]:  {df.iloc[-1]['date'].date()}  收盘 {df.iloc[-1]['close']}")  # 最后1行
print(f"loc最近5天:\n{df.loc[df['date'] >= df['date'].max() - pd.Timedelta(days=10), ['date','close']].tail(5)}")

# ============================================================
# 3. rolling / shift / pct_change / diff
# ============================================================
df["ma5"] = df["close"].rolling(5).mean()           # 5日均线（含当日）
df["ma20"] = df["close"].rolling(20).mean()          # 20日均线（含当日）
df["return"] = df["close"].pct_change()              # 日收益率
df["price_change"] = df["close"].diff()              # 价格变动（元）

# ★ 关键：前视偏差修正 —— shift(1)
df["ma20_signal"] = df["close"].rolling(20).mean().shift(1)  # 用T-1日的均线做T日信号
# 注意：ma20 含当天数据 → 前视偏差；ma20_signal 不含 → 正确的回测信号

print("\n=== rolling(20).mean().shift(1) 对比 ===")
compare = df[["date", "close", "ma20", "ma20_signal"]].tail(5)
print(compare.to_string())

# ============================================================
# 4. merge（模拟：合并指数基准）
# ============================================================
benchmark = df[["date", "close"]].copy()
benchmark["bench_close"] = benchmark["close"] * 1.05  # 简化演示
merged = df.merge(benchmark[["date", "bench_close"]], on="date", how="left")
merged["excess"] = merged["return"] - merged["bench_close"].pct_change()
print(f"\n合并后列数: {len(merged.columns)}，超额收益列已生成")

# ============================================================
# 5. groupby / resample
# ============================================================
df["year"] = df["date"].dt.year
yearly = df.groupby("year")["return"].agg(["mean", "std", "count"])
print("\n=== 分年日收益统计 ===")
print(yearly.round(6))

monthly_return = df.set_index("date")["return"].resample("ME").apply(
    lambda x: (1 + x).prod() - 1
)  # 月度收益
print(f"\n最近6个月收益率:\n{monthly_return.tail(6).round(4)}")

# ============================================================
# 6. 练习输出：收益均值、标准差、最大单日跌幅
# ============================================================
returns = df["return"].dropna()
print("\n=== 收益统计 ===")
print(f"日收益均值:      {returns.mean():.6f}  ({returns.mean()*100:.4f}%)")
print(f"日收益标准差:    {returns.std():.6f}  ({returns.std()*100:.4f}%)")
print(f"最大单日涨幅:     {returns.max():.4%}")
print(f"最大单日跌幅:     {returns.min():.4%}")
print(f"年化收益(估算):   {returns.mean()*252:.4%}")
print(f"年化波动(估算):   {returns.std()*np.sqrt(252):.4%}")
print(f"夏普比(估算):     {(returns.mean()/returns.std())*np.sqrt(252):.2f}")

# ============================================================
# 7. 自检：rolling(20).mean().shift(1) 为什么 shift(1) 不能省？
# ============================================================
print("\n=== 自检：为什么 rolling(20).mean().shift(1) 里 shift(1) 不能省？ ===")
print("""
不加 shift(1)：ma20 包含了当天收盘价 → 用当天收盘价算出信号、再"当天"成交
              → 实际不可实现（收盘价收盘后才能知道）→ 前视偏差

加 shift(1)：  ma20 只用到了昨天及以前的数据 → 信号在 T 日开盘前就已知
              → T 日开盘即可交易 → 真实可实现的回测

这是防止回测虚高最基本的一步。""")