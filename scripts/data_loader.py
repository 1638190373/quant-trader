# -*- coding: utf-8 -*-
"""D13 统一数据入口：以后回测/研究代码只从这里取数，不直接碰文件。
用法：
    from data_loader import load_panel, load_stock, trading_calendar
    df = load_panel(codes=['sh600519'], start='2024-01-01', end='2025-10-31')
"""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "data", "panel.parquet")

def load_panel(codes=None, start=None, end=None):
    df = pd.read_parquet(PANEL)
    if codes is not None:
        df = df[df["code"].isin(codes)]
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)

def load_stock(code, start=None, end=None):
    return load_panel([code], start, end)

def trading_calendar(start=None, end=None):
    cal = pd.read_csv(os.path.join(ROOT, "data", "交易日历.csv"), encoding="gbk")
    cal["trade_date"] = pd.to_datetime(cal["trade_date"])
    if start: cal = cal[cal["trade_date"] >= pd.Timestamp(start)]
    if end:   cal = cal[cal["trade_date"] <= pd.Timestamp(end)]
    return pd.DatetimeIndex(cal["trade_date"].sort_values())
