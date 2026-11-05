# -*- coding: utf-8 -*-
"""
D15 回测引擎(一)：七个类的设计骨架
====================================
数据流（单向流水线）：

  panel数据 → [Backtester主循环·逐日取帧]
      → 递出 BarData(今天这根K线)
      → Strategy.on_bar() 返回 意向清单[Order]      ← 策略只出主意
      → 撮合(过六道安检: 停牌/涨跌停/现金/整手/滑点/费用) ← 引擎执行
      → 生成 Fill(成交回执)
      → 更新 Position(持仓台账) 与 Portfolio(总账本)
      → 收盘记一行净值
  循环1412次 → 净值序列 → 绩效指标(D18)

铁律（写死在结构里，不靠记性）：
  T日收盘产生的信号 → T+1日开盘撮合。Strategy拿不到明天，
  撮合收不到今天收盘前的意向 —— 物理防前视(D2/D5/D7/D8四次教训)。

D15完成：七个类=格式定义；D16补：Backtester.run()主循环。
"""


# ============ ① BarData：K线记录表（一帧画面） ============
class BarData:
    """某一天的某只股票：开高低收量 + 当日交易状态。纯数据，无判断。"""

    def __init__(self, code, date, open_, high, low, close, volume,
                 suspended=False, limit_up=None, limit_down=None):
        self.code = code              # "sh600519"
        self.date = date              # 这一帧是哪天
        self.open = open_             # 开盘价（撮合用它：信号T日、成交T+1开盘）
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.suspended = suspended    # 停牌 → 撮合第一关直接拒
        # 涨/跌停价（主板±10%，创业板/科创±20%；主循环按板块算好传入）
        self.limit_up = limit_up
        self.limit_down = limit_down


# ============ ② Order：订单申请表（策略的"意愿书"） ============
class Order:
    """策略想做什么。注意：它只是申请，能不能成、成多少由撮合决定。"""

    STATUS_NEW = "待撮合"
    STATUS_FILLED = "已成交"
    STATUS_PART = "部分成交"
    STATUS_REJECTED = "被拒"          # 拒单原因必须记录，D34运维要用

    def __init__(self, code, direction, style, value, reason=""):
        self.code = code
        self.direction = direction      # "buy" / "sell"
        self.style = style              # "value"按金额 / "target_value"调到市值 / "target"调到股数
        self.value = value              # 对应金额或数量
        self.reason = reason            # 为什么下这单（日志/复盘用）
        self.status = self.STATUS_NEW
        self.reject_reason = ""


# ============ ③ Fill：成交回执单（事实，不是意愿） ============
class Fill:
    """撮合成功后开出的回执：真实价、真实量、真实费用。账本只认Fill。"""

    def __init__(self, code, date, direction, price, volume,
                 commission=0.0, tax=0.0, slippage_cost=0.0):
        self.code = code
        self.date = date
        self.direction = direction
        self.price = price              # 含滑点的成交价 = 参考价 x (1±0.1%)
        self.volume = volume            # 已向下取整到100股(一手)后的真实成交数
        self.commission = commission    # 佣金(万三,最低5元) → 要从现金扣
        self.tax = tax                  # 印花税(只在卖出,万五) → 要从现金扣
        # ★滑点损耗：纯统计字段，【不扣第二次】！
        #   它 = (成交价-参考价)×数量，已经包含在 self.price 里扣过了。
        #   单列出来只为D18算"成本占毛收益比"，账本绝不能再减它。
        self.slippage_cost = slippage_cost

    @property
    def total_cost(self):
        return self.commission + self.tax


# ============ ④ Position：持仓登记表（一只票一本台账） ============
class Position:
    """T+1的物理载体：今日买入量不可卖。可卖数量 = 总量 - 今日买入。"""

    def __init__(self, code):
        self.code = code
        self.quantity = 0               # 总持仓股数
        self.today_bought = 0           # 当日买入（次日归零 → 解锁可卖）
        self.avg_cost = 0.0             # 持仓均价(摊薄成本)，止损判断用它

    @property
    def sellable(self):                 # 可卖数量：T+1就卡在这
        return self.quantity - self.today_bought

    def on_new_day(self):               # 引擎每天开盘前调用：昨日买入今日解锁
        self.today_bought = 0

    def update_buy(self, vol, price, cost):
        """买入后重新摊薄成本：(旧市值+新市值+新费用)/(旧量+新量)。"""
        old_value = self.avg_cost * self.quantity
        self.quantity += vol
        self.today_bought += vol
        self.avg_cost = (old_value + price * vol + cost) / self.quantity

    def update_sell(self, vol, cost):
        """卖出只减量；清仓则重置均价。"""
        self.quantity -= vol
        if self.quantity == 0:
            self.avg_cost = 0.0


# ============ ⑤ Portfolio：总账本 ============
class Portfolio:
    """现金 + 全部持仓 + 每日净值历史。"""

    def __init__(self, initial_cash):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {}             # {code: Position} —— D1学的字典
        self.equity_history = []        # [(date, 总资产), ...] → 最后这就是净值曲线

    def get_or_create(self, code):
        if code not in self.positions:
            self.positions[code] = Position(code)
        return self.positions[code]

    def market_value(self, bars_today):
        """持仓市值 = Σ(持仓量 × 今日收盘价)。bars_today: {code: BarData}"""
        total = 0.0
        for code, pos in self.positions.items():
            if pos.quantity > 0 and code in bars_today:
                total += pos.quantity * bars_today[code].close
        return total

    def total_value(self, bars_today):
        return self.cash + self.market_value(bars_today)

    def new_day(self, date, bars_today):
        """每天收盘后记账：持仓解锁T+1 + 记一行净值。"""
        for pos in self.positions.values():
            pos.on_new_day()
        self.equity_history.append((date, self.total_value(bars_today)))


# ============ ⑥ Strategy：策略基类（填空模板） ============
class Strategy:
    """以后的所有策略都继承它，只填 on_bar —— 权责分离：只出意向清单。"""

    def on_init(self, backtester):
        """回测开始前调一次：加载历史、算指标（对应聚宽initialize）。"""
        pass

    def on_bar(self, bar, portfolio, indicators):
        """
        每个交易日被引擎调用一次，返回意向清单。
        bar         : 今日K线（含停牌/涨跌停信息）
        portfolio   : 当前账本（查持仓、查现金）
        indicators  : 引擎算好的昨日至今指标快照（如昨天下轨/昨收）——
                      "过去信息"由引擎显式递进来，策略不许自己伸手拿数据，
                      从接口上断掉"顺手取今天"的可能
        返回        : list[Order]，空列表 = 不动作
        """
        return []


# ============ ⑦ Backtester：总调度（放映员 + 传送带） ============
class Backtester:
    """
    持有数据、策略、账本、成本参数，逐日驱动全流程。
    run()主循环(D16实现)的骨架伪代码：

      for date in 交易日:
          1. 从panel取今天全部BarData → bars_today
          2. portfolio.new_day(date)   → T+1解锁
          3. 撮合【昨天收下的】意向单   → 用今天的open过六道安检 → Fill → 改账本
          4. 调 strategy.on_bar(今天的bar, 账本, 指标快照)
             → 收下新意向单，压进队列（明天开盘才执行！）
          5. 收盘记净值
      返回 equity_history + 每笔Fill明细

    ★ 第3步在第4步【前面】：今天执行的永远是昨天的信号
      —— 前视偏差在结构上不可能发生（对照D7实验的130个点）。
    """

    def __init__(self, panel, strategy, initial_cash=100000.0,
                 commission_rate=0.0003, min_commission=5.0,
                 stamp_tax=0.0005, slippage_pct=0.002):
        self.panel = panel              # D13 load_panel() 返回的DataFrame
        self.strategy = strategy        # Strategy的子类实例
        self.portfolio = Portfolio(initial_cash)
        # ---- 成本参数全显式传入，不许有隐藏的"默认免费"（D5教训） ----
        self.commission_rate = commission_rate   # 佣金万三
        self.min_commission = min_commission     # 单笔最低5元
        self.stamp_tax = stamp_tax               # 印花税卖出万五
        self.slippage_pct = slippage_pct         # 0.2%/双边(买贵0.1%卖低0.1%)
        self.pending_orders = []        # 意向队列：今天收，明天开盘撮合
        self.fills = []                 # 全部成交回执（D18算成本占比用）
        self.blocked = {"limit_up_buy": 0, "limit_down_sell": 0,
                        "suspended": 0, "cash": 0}   # 拦截计数（D6同款）

    def run(self):
        raise NotImplementedError("D16 实现主循环 —— 今天先把七个格式定下来")

    def report(self):
        """净值序列 → 年化/最大回撤/夏普（D5已手工做过，D18封装成函数）。"""
        raise NotImplementedError("D16/D18 实现")
