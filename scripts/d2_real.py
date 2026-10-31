import pandas as pd

# 读本地CSV —— 不再联网，永远不会报刚才那种错
df = pd.read_csv("maotai.csv")

print(df.shape)        # 几个交易日、几列
print(df.head(3))      # 前3行
print(df["收盘"].mean())   # 平均收盘价

# 1. 5日均线
df["ma5"] =df["收盘"].rolling(5).mean()

# 2. 日收益率
df["ret"] = df["收盘"].pct_change()

# 3. 修正前视偏差的信号版均线
df["ma5_signal"] =df["收盘"].rolling(5).mean().shift(1)

# 4. 输出：收益率的均值、标准差、最大单日跌幅
print("收益均值:", df["ret"].mean())
print("收益标准差:", df["ret"].std())
print("最大单日跌幅:", df["ret"].min())

# 看一眼结果：均线前4天、收益第1天应该是NaN——你认识了的新朋友
print(df[["日期", "收盘", "ma5", "ma5_signal", "ret"]].head(6))