# -*- coding: utf-8 -*-
"""
D12 数据层(一)：拉数据
========================
任务：300只现役成分股 + 退市股票池，5年日线，落地本地文件。

三个工程要点（都写在函数里，注释标了为什么）：
  1. 限速：每只票之间 sleep，防止像上次那样触发 Push2RateLimitError 封禁
  2. 重试：单只票失败自动重试2次，网络抖一下不至于整个批次报废
  3. 断点续传：已存在本地文件的票直接跳过——跑到一半断电/断网，
     重跑本脚本会自动从断点继续，不会重复拉（这就是"幂等"的雏形）

股票池为什么这么组（对应 D8 报告遗留的"近似池"问题）：
  A组 沪深300现役成分股300只 —— 幸存者池（有前复权qfq数据）
  B组 2022~2025年间退市的票   —— 含死者池（用不复权真实价，退市后自然没数据）
  两组合起来回测，才是"当时的真实市场"，幸存者偏差可量化修正。

数据口径（写进数据字典）：A组前复权qfq，B组不复权（退市票要的是归零真实过程）。
"""
import os, sys, time, json
import socket                       # D12修复: 全局网络超时保护
socket.setdefaulttimeout(20)        # 任何请求挂起20秒即抛异常→被下面的重试接住
import pandas as pd
import akshare as ak

# ---------- 路径 ----------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)

START, END = "20200101", "20251031"      # 5年窗口，与计划自检标准一致
SLEEP = 0.6                              # 限速：每只票间隔0.6秒（新浪接口经验值）

# ---------- 第1步：列名单 ----------
def build_pool():
    pool = []   # [(证券代码sina格式, 名称, 组别)]

    # A组：沪深300现役成分股
    cs = ak.index_stock_cons_csindex(symbol="000300")
    for _, r in cs.iterrows():
        code = str(r["成分券代码"]).zfill(6)
        pool.append((to_sina(code), r["成分券名称"], "csi300"))

    # B组：2022~2025退市的票（D8清单来源），最多取100只
    dl = pd.read_csv(os.path.join(DATA_DIR, "退市名单.csv"))
    dl["delist_date"] = pd.to_datetime(dl["delist_date"], errors="coerce")
    dl = dl[(dl["delist_date"] >= "2022-01-01") & (dl["delist_date"] <= "2025-10-31")]
    dl = dl[~dl["code"].astype(str).str.startswith("2")]   # B股(200开头)新浪数据差，剔除
    for _, r in dl.head(100).iterrows():
        pool.append((to_sina(str(r["code"]).zfill(6)), r["name"], "delisted"))

    return pool

def to_sina(code6):
    """6位代码 → 新浪格式：60/68开头沪市sh，00/30开头深市sz"""
    return ("sh" if code6.startswith(("60", "68")) else "sz") + code6

# ---------- 第2步：拉数据（限速+重试+断点续传） ----------
def fetch_one(sym, name, group):
    path = os.path.join(RAW_DIR, f"{sym}.csv")
    if os.path.exists(path):                 # 断点续传：有文件就跳过
        return "skip"
    adjust = "qfq" if group == "csi300" else ""   # 数据口径：幸存者前复权/退市不复权
    for attempt in range(3):                 # 重试2次+首发1次
        try:
            d = ak.stock_zh_a_daily(symbol=sym, start_date=START,
                                    end_date=END, adjust=adjust)
            if d is None or len(d) == 0:
                return "empty"               # 退市太早/接口无记录
            d = d.reset_index()[["date", "open", "high", "low", "close", "volume"]]
            d.insert(0, "code", sym)
            d.insert(1, "name", name)
            d.insert(2, "group", group)
            d.to_csv(path, index=False)      # 一只一个文件，先求稳（D13再合成Parquet库）
            return "ok"
        except Exception as e:
            if attempt < 2:
                time.sleep(2 + attempt * 4)  # 指数退避雏形：失败后多等一会再试
            else:
                return f"fail:{type(e).__name__}"
    return "fail"

# ---------- 第3步：指数日线 + 交易日历（回测基准与时序骨架） ----------
def fetch_index_and_calendar():
    p1 = os.path.join(RAW_DIR, "index_sh000300.csv")
    if not os.path.exists(p1):
        ak.stock_zh_index_daily(symbol="sh000300") \
          .to_csv(p1, index=False)
    p2 = os.path.join(DATA_DIR, "交易日历.csv")
    if not os.path.exists(p2):
        ak.tool_trade_date_hist_sina().to_csv(p2, index=False)

# ---------- 主流程 ----------
if __name__ == "__main__":
    print("== 组装股票池 ==")
    pool = build_pool()
    print(f"股票池: {len(pool)} 只 "
          f"(csi300={sum(1 for x in pool if x[2]=='csi300')}, "
          f"delisted={sum(1 for x in pool if x[2]=='delisted')})")

    # 名单本身也是数据资产，落两份：json给程序读，csv给你核对
    with open(os.path.join(DATA_DIR, "股票池.json"), "w", encoding="utf-8") as f:
        json.dump([{"code": c, "name": n, "group": g} for c, n, g in pool],
                  f, ensure_ascii=False, indent=1)
    pd.DataFrame(pool, columns=["sina代码", "名称", "组别"]) \
      .to_csv(os.path.join(DATA_DIR, "股票池.csv"), index=False, encoding="utf-8-sig")

    print("== 开始拉取（进度每20只报一次，可放心中断重跑）==")
    stat = {"ok": 0, "skip": 0, "empty": 0, "fail": 0}
    fails = []
    for i, (sym, name, group) in enumerate(pool, 1):
        r = fetch_one(sym, name, group)
        key = r.split(":")[0]
        stat[key] = stat.get(key, 0) + 1
        if key == "fail":
            fails.append(f"{sym} {name} {r}")
        if i % 20 == 0:
            print(f"  进度 {i}/{len(pool)} | 成功{stat['ok']} 跳过{stat['skip']} "
                  f"空{stat['empty']} 失败{stat['fail']}", flush=True)
        time.sleep(SLEEP)                    # 限速，防封

    fetch_index_and_calendar()
    print(f"\n== 完成 ==\n统计: {stat}")
    if fails:
        print("失败清单（重跑本脚本会自动重试这些）:")
        for x in fails[:20]:
            print("  ", x)
