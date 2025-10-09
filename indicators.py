"""技术指标计算模块

提供简单且可扩展的 EMA、SMA 计算与交叉判断工具函数。
"""
from __future__ import annotations

from dataclasses import dataclass
import typing as t


def sma(values: list[float], period: int) -> list[float]:
    """简单移动平均 (SMA)。返回与输入等长的列表，前期不足的用 None 填充。"""
    out: list[float] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) < period:
            out.append(None)
        else:
            out.append(sum(window) / period)
    return out


def ema(values: list[float], period: int) -> list[float]:
    """指数移动平均 (EMA)。返回与输入等长的列表，前期不足的用 None 填充。

    与主流交易所（含 Binance）一致：
    - 使用前 `period` 根的 SMA 作为 EMA 初始值；
    - 后续 EMA_t = price_t * k + EMA_{t-1} * (1-k)，其中 k = 2/(period+1)。
    """
    if period <= 0:
        raise ValueError("period must be > 0")
    out: list[float] = []
    k = 2 / (period + 1)
    ema_prev: float | None = None
    for i, v in enumerate(values):
        if i < period - 1:
            # 前期不足，填 None
            out.append(None)
            continue
        if i == period - 1:
            # 以首个完整窗口的 SMA 作为初始 EMA
            window = values[:period]
            ema_prev = sum(window) / period
            out.append(ema_prev)
            continue
        # 正常迭代
        ema_curr = v * k + (ema_prev if ema_prev is not None else v) * (1 - k)
        ema_prev = ema_curr
        out.append(ema_curr)
    return out


@dataclass
class CrossSignal:
    golden_cross: bool
    death_cross: bool


def crossover(ema_list: list[float], ma_list: list[float]) -> CrossSignal:
    """判断金叉/死叉。仅在最近两个点均有效时判断。

    - 金叉：前一根 EMA <= MA 且当前 EMA > MA
    - 死叉：前一根 EMA >= MA 且当前 EMA < MA
    """
    if not ema_list or not ma_list:
        return CrossSignal(False, False)
    if len(ema_list) < 2 or len(ma_list) < 2:
        return CrossSignal(False, False)

    prev_ema, curr_ema = ema_list[-2], ema_list[-1]
    prev_ma, curr_ma = ma_list[-2], ma_list[-1]
    if prev_ema is None or curr_ema is None or prev_ma is None or curr_ma is None:
        return CrossSignal(False, False)

    golden = prev_ema <= prev_ma and curr_ema > curr_ma
    death = prev_ema >= prev_ma and curr_ema < curr_ma
    return CrossSignal(golden_cross=golden, death_cross=death)


def is_rising(series: list[float], lookback: int = 3) -> bool:
    """判断指标是否呈上升趋势：最近 lookback 根单调非降。"""
    vals = [v for v in series[-lookback:] if v is not None]
    if len(vals) < lookback:
        return False
    return all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))


def ema_slope(series: list[float], lookback: int, mode: str = "mean_diff", normalize_by_ema: bool = True) -> float | None:
    """计算 EMA 的斜率强度。

    参数：
    - lookback: 回看根数（>=2）。
    - mode: "mean_diff"（近 N 根差值均值）或 "linreg"（线性回归拟合斜率）。
    - normalize_by_ema: 是否除以当前 EMA 做归一化，提升跨价格区间的可比性。

    返回：
    - 每根K线的单位斜率（若 normalize_by_ema=True，则为相对斜率）。
    - 数据不足时返回 None。
    """
    if lookback is None or lookback < 2:
        return None
    vals = [v for v in series[-lookback:] if v is not None]
    if len(vals) < lookback:
        return None
    curr = vals[-1]

    if mode == "linreg":
        # 线性回归拟合：x=0..N-1, y=EMA
        n = len(vals)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(vals) / n
        var_x = sum((x - mean_x) ** 2 for x in xs)
        if var_x == 0:
            return None
        cov_xy = sum((xs[i] - mean_x) * (vals[i] - mean_y) for i in range(n))
        slope = cov_xy / var_x
    else:
        # 默认均值差分：更灵敏
        diffs = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
        slope = sum(diffs) / len(diffs)

    if normalize_by_ema and curr and curr != 0:
        slope = slope / curr
    return slope


def slope_ok(series: list[float], lookback: int, min_slope: float, *, mode: str = "mean_diff", normalize_by_ema: bool = True, strict_monotonic: bool = False) -> tuple[bool, bool]:
    """返回 (long_ok, short_ok) 斜率门槛是否满足。

    - long_ok: slope >= min_slope 且（如 strict_monotonic）最近 N 根严格递增。
    - short_ok: slope <= -min_slope 且（如 strict_monotonic）最近 N 根严格递减。
    """
    s = ema_slope(series, lookback=lookback, mode=mode, normalize_by_ema=normalize_by_ema)
    if s is None:
        return (False, False)
    long_ok = s >= float(min_slope)
    short_ok = s <= -float(min_slope)
    if strict_monotonic:
        vals = [v for v in series[-lookback:] if v is not None]
        if len(vals) < lookback:
            return (False, False)
        inc_ok = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
        dec_ok = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
        long_ok = long_ok and inc_ok
        short_ok = short_ok and dec_ok
    return (long_ok, short_ok)