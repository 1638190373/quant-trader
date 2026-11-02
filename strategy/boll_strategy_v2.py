# -*- coding: utf-8 -*-
"""
布林带超跌反弹策略 v2 —— 标准骨架重写版（D4作业）

相对 v1（AI原版）的修复：
  修复bug①：run_daily 取消注释，策略真正会执行
  修复bug②：布林带改用【日线】计算（原版用1分钟线，窗口只有20分钟）
  修复bug④：用聚宽的 attribute_history 自动按【交易日】取数，
             不再用 timedelta(days=1) 自然日（原版周一会找错"昨天"）
  修复bug⑤：买入前先检查可用现金，同日多只触发不会超买
  新增：最小止损（成本价下方6%无条件卖出）——补上"买完阴跌永远不卖"的窟窿
        （阶段3 D21-D23 会把它扩展成正式风控模块）

防前视设计（对应D2学的 shift(1)）：
  - attribute_history(stock, N, '1d') 在 14:55 调用时，返回的是【截至昨天】
    的 N 根完整日线（今天的日线还没走完，不含今天）→ 昨日均线天然无未来数据
  - 今日下轨 = 最近19根日线收盘 + 当前实时价，14:55 时实时价是可得信息，合法
"""

from jqdata import *
import numpy as np

# ==========================================
# 策略参数（自由参数共3个：BB_PERIOD、BB_STD、入场带宽阈值；
# 止损6%和仓位30%属于风控参数——总数压在线内）
# ==========================================
BB_PERIOD = 20          # 布林带窗口：20个交易日
BB_STD = 2.0            # 上下轨 = 中轨 ± 2倍标准差
BB_WIDTH_THRESH = 10    # 带宽下限：(上轨-下轨)/中轨*100 要大于10才入场
POSITION_RATIO = 0.3    # 单笔最多动用总资产30%
STOP_LOSS = 0.06        # 止损线：跌破成本价6%无条件卖出

STOCK_POOL = [
    '600519.XSHG', '601318.XSHG', '600036.XSHG', '600030.XSHG', '000858.XSHE',
    '000333.XSHE', '601166.XSHG', '600900.XSHG', '600276.XSHG', '601888.XSHG',
    '300750.XSHE', '300059.XSHE', '002475.XSHE', '002594.XSHE', '601012.XSHG',
    '601899.XSHG', '000002.XSHE', '002415.XSHE', '000651.XSHE', '000001.XSHE',
    '601088.XSHG', '600309.XSHG', '601601.XSHG', '601668.XSHG', '600048.XSHG',
    '600919.XSHG', '601398.XSHG', '601288.XSHG', '600887.XSHG', '600809.XSHG',
]  # 演示时精简为30只，跑通后可换回100只全池


def initialize(context):
    """整个回测只执行1次：定规矩"""
    set_option('use_real_price', True)        # 用真实价格回测
    set_option('avoid_future_data', True)     # 平台级防前视兜底
    set_benchmark('000300.XSHG')              # 基准=沪深300，只跟它比超额

    # 双边佣金万三、卖出印花税万五、单笔最低5元（A股真实成本）
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.0005,
        open_commission=0.0003, close_commission=0.0003,
        min_commission=5), type='stock')
    # 滑点：按价格的0.2%计（D5自查发现v1/v2初版都写错了：
    # FixedSlippage(0.002) 的含义是"每股固定滑0.002元"——
    # 对43元的股票等于0.005%滑点，约等于没有，是假回测。
    # PriceRelatedSlippage(0.002) 才是"价格的0.2%"：买贵0.1%、卖便宜0.1%）
    set_slippage(PriceRelatedSlippage(0.002))

    # ★ 修复bug①：注册每日14:55定时任务，这行必须生效
    run_daily(check_signals, time='14:55')

    # D6：A股交易制度约束——被拦下的订单计数器
    g.blocked_buy = 0    # 涨停不追买
    g.blocked_sell = 0   # 跌停卖不出
    run_daily(report_blocked, time='15:30')


def report_blocked(context):
    """收盘后汇报：累计被拦订单数（计划D6要求的'打印被拦下的订单数'）"""
    log.info(f"📊 累计拦截 | 涨停不追买: {g.blocked_buy} 笔 | 跌停卖不出: {g.blocked_sell} 笔")


def check_signals(context):
    """每天14:55对股票池跑一遍"""
    current_data = get_current_data()   # 一次性取全池实时数据，比循环里逐只取接口快

    for stock in STOCK_POOL:

        # ---- T+1：今天刚买的不允许卖 ----
        # 注意：必须先用 in 判断再取。直接 .get() 也会触发聚宽
        # "positions中不存在，返回空Position" 的海量WARNING刷屏
        pos = context.portfolio.positions[stock] \
            if stock in context.portfolio.positions else None
        if pos is not None and pos.today_amount > 0 and pos.closeable_amount == 0:
            continue

        # ★ 修复bug②+bug④：按【交易日】取截至昨天的20根完整日线
        # 14:55时今日日线未走完，attribute_history自动只给历史完整日
        hist = attribute_history(stock, BB_PERIOD, '1d', ['close'],
                                 skip_paused=True)
        if len(hist) < BB_PERIOD:
            continue  # 新股/长期停牌凑不满窗口，跳过

        closes = hist['close'].values          # 截至昨天的20个收盘价
        y_price = closes[-1]                   # 昨日收盘价
        y_mid = np.mean(closes)
        y_std = np.std(closes, ddof=1)
        y_down = y_mid - BB_STD * y_std
        y_up = y_mid + BB_STD * y_std

        # 今日实时价（14:55当下可得的价，无未来数据）
        t_price = current_data[stock].last_price
        if t_price == 0:                       # 全天停牌
            continue

        # 今日布林带 = 昨天起往前19个交易日 + 今日实时价（窗口右端滑到"今天"）
        c20 = np.append(closes[1:], t_price)
        t_mid = np.mean(c20)
        t_std = np.std(c20, ddof=1)
        t_up = t_mid + BB_STD * t_std
        t_down = t_mid - BB_STD * t_std

        # 涨跌幅：和昨日收盘比（D1写的calc_return在这里）
        pct = (t_price - y_price) / y_price

        # ============ 卖出（先判卖再判买，避免同一轮买卖打架） ============
        if pos is not None and pos.total_amount > 0:
            # D6: 跌停卖不出——现价已打到跌停价，挂单也成交不了，跳过并计数
            if t_price <= current_data[stock].low_limit:
                g.blocked_sell += 1
                log.info(f"🚫 跌停卖不出 {stock} 现价{t_price:.2f}=跌停价")
                continue
            # ① 原逻辑：昨冲高过上轨、今回落 → 反弹结束清仓
            if y_price > y_up and t_price < t_up:
                order_target(stock, 0)
                log.info(f"🔴 止盈卖出 {stock} 昨冲高轨今回落 现价{t_price:.2f}")
            # ② 新增止损：亏过成本价6%无条件走人（堵原版"永不卖出"的窟窿）
            elif t_price < pos.avg_cost * (1 - STOP_LOSS):
                order_target(stock, 0)
                log.info(f"⚠️ 止损卖出 {stock} 成本{pos.avg_cost:.2f}→现价{t_price:.2f}")
            continue  # 持仓股不再考虑加仓

        # ============ 买入 ============
        bounced = (y_price < y_down) and (t_price > t_down)   # 昨破下轨、今收回
        wide_enough = (t_up - t_down) / t_mid * 100 > BB_WIDTH_THRESH  # 波动够肥
        not_crash = pct > -0.08                               # 今日没暴跌8%

        if bounced and wide_enough and not_crash:
            # D6: 涨停不追买——现价打到涨停价，排队买不到，跳过并计数
            if t_price >= current_data[stock].high_limit:
                g.blocked_buy += 1
                log.info(f"🚫 涨停不追买 {stock} 现价{t_price:.2f}=涨停价")
                continue
            # ★ 修复bug⑤：目标市值取"总资产30%"与"可用现金"的较小者
            buy_cash = min(context.portfolio.total_value * POSITION_RATIO,
                           context.portfolio.available_cash)
            if buy_cash > 1000:   # 现金太少连1000股都买不起就不折腾
                order_value(stock, buy_cash)
                log.info(f"🟢 买入 {stock} 现价{t_price:.2f} 今日{pct:.2%} 昨日超跌")
