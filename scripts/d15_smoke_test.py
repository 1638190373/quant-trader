# -*- coding: utf-8 -*-
"""D15 冒烟测试：验证七个类"装得起来"（不测策略逻辑，主循环还没有）。"""
import sys
import datetime as dt
sys.path.insert(0, "backtest")
from engine import BarData, Order, Fill, Position, Portfolio, Strategy, Backtester

print("== 1. BarData：一帧K线 ==")
bar = BarData("sh600519", dt.date(2024, 10, 8),
              37.0, 37.8, 36.6, 37.5, 30000,
              limit_up=41.25, limit_down=33.75)
print(f"  茅台 {bar.date} 收{bar.close} 涨停{bar.limit_up} 停牌={bar.suspended}")

print("== 2. Order/Fill：意愿与回执分离 ==")
o = Order("sh600519", "buy", "value", 30000, reason="昨跌破下轨今收回")
print(f"  订单: {o.direction} {o.style} {o.value} 状态={o.status}")
f = Fill("sh600519", dt.date(2024, 10, 9), "buy",
         price=37.54, volume=700, commission=7.88, slippage_cost=26.25)
print(f"  回执: 成交{f.volume}股@{f.price} 佣金{f.commission} 滑点损耗{f.slippage_cost}")

print("== 3. Position：T+1物理载体 ==")
pos = Position("sh600519")
pos.update_buy(700, 37.54, 7.88)
print(f"  买入700股后: 总量={pos.quantity} 可卖={pos.sellable} ← 今天买的今天卖不了")
pos.on_new_day()
print(f"  过一夜解锁: 可卖={pos.sellable} 摊薄成本={pos.avg_cost:.3f}(含费)")

print("== 4. Portfolio：账本记净值 ==")
pf = Portfolio(100000.0)
pf.cash -= 37.54 * 700 + 7.88
p = pf.get_or_create("sh600519")
p.update_buy(700, 37.54, 7.88)
bars = {bar.code: bar}                      # 收盘价37.5
pf.new_day(dt.date(2024, 10, 8), bars)
print(f"  现金{pf.cash:.2f} + 市值{700*37.5:.2f} = 总资产{pf.total_value(bars):.2f}")
print(f"  净值历史{pf.equity_history}")

print("== 5. Backtester：装配(主循环待D16) ==")
bt = Backtester(panel=None, strategy=Strategy(), initial_cash=100000.0)
print(f"  成本参数: 佣金万{bt.commission_rate*10000:.0f} 最低{bt.min_commission} "
      f"印花万{bt.stamp_tax*10000:.0f} 滑点{bt.slippage_pct*100:.1f}%/双边")
print(f"  拦截计数: {bt.blocked}")
try:
    bt.run()
except NotImplementedError as e:
    print(f"  run()未实现(符合预期): {e}")

print("\n七个类全部装配成功 —— D15骨架完成，D16接主循环")
