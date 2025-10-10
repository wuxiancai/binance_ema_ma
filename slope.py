"""斜率参数推荐预设（可直接复制到 config.jsonc 的 indicators.slope）

目标：面向 1m / 5m / 15m 周期，搭配 EMA(5) 与 MA(15/20/30/50)，提供最优/稳健的斜率默认值。

使用方式：
- 从本文件中找到与你图表周期与均线周期匹配的预设，复制其字典内容到 `config.jsonc` 的：
  "indicators": {
    ...,
    "slope": {  ← 将下方对应的 dict 粘贴到这里
      ...
    }
  }

斜率字段含义与建议：
- mode: 斜率计算方式
  - "linreg"：最近 N 根做线性回归的拟合斜率（更抗噪，推荐）。
  - "mean_diff"：最近 N 根 EMA 的相邻差值均值（更灵敏）。
- lookback: 回看根数 N（N 越大越稳健但更滞后）。
- normalize_by_ema: 是否做斜率归一化（斜率/当前 EMA），跨价格区间更可比，推荐 true。
- min_slope: 斜率强度门槛（每根K线的单位斜率）。
  - 开多要求 slope >= min_slope；开空要求 slope <= -min_slope。
- strict_monotonic: 是否要求最近 N 根严格递增/递减（趋势确认更稳健，建议在较长周期或强趋势时开启）。

数值范围经验（BTCUSDT 合约为例，可据此微调）：
- 1m：min_slope ~ 0.00006–0.00012（默认 0.00008）
- 5m：min_slope ~ 0.00012–0.00025（默认 0.00018）
- 15m：min_slope ~ 0.00020–0.00040（默认 0.00028）

说明：斜率已做归一化（默认 true），相对不同价格区间更稳定；若你交易的是波动更剧烈或更平缓的币对，可相应提高或降低 min_slope。
"""

from typing import Dict, Any


# 预设参数（按 周期 × EMA5 + MA{15,20,30,50} 组合）
# 注意：斜率与 MA 周期并非强绑定，多数情况下同一时间周期的斜率门槛可以在不同 MA 周期复用；
# 为便于精细化，这里仍给出每个组合的推荐默认值与注释。
PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    # ============================= 1m =============================
    "1m": {
        # 灵敏度最高、噪声也最大；推荐 linreg + N=4，min_slope 取中位值。
        "EMA5MA15": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00008,  # 备选：0.00006（更激进）/ 0.00010–0.00012（更稳健）
            "strict_monotonic": False,  # 备选：True（过滤横盘反复，但滞后更大）
        },
        "EMA5MA20": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00008,  # 与 MA15 基本一致；更强调趋势可取 0.00010
            "strict_monotonic": False,
        },
        "EMA5MA30": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00009,  # MA 更长，交叉更慢；略微提高强度更稳健
            "strict_monotonic": False,
        },
        "EMA5MA50": {
            "mode": "linreg",
            "lookback": 5,  # N=5 增强稳健，降低误触发
            "normalize_by_ema": True,
            "min_slope": 0.00010,  # 备选：0.00012 在强趋势过滤更好
            "strict_monotonic": False,
        },
    },

    # ============================= 5m =============================
    "5m": {
        # 噪声显著降低；建议提高 min_slope，N 取 4 或 5。
        "EMA5MA15": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00018,  # 备选：0.00015（更灵敏）/ 0.00022（更稳健）
            "strict_monotonic": False,
        },
        "EMA5MA20": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00018,  # 与 MA15 基本一致；趋势强时可取 0.00020–0.00022
            "strict_monotonic": False,
        },
        "EMA5MA30": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00020,  # MA 越长，交叉越慢；适度提高强度
            "strict_monotonic": False,
        },
        "EMA5MA50": {
            "mode": "linreg",
            "lookback": 5,
            "normalize_by_ema": True,
            "min_slope": 0.00022,  # 备选：0.00025（强趋势过滤更好）
            "strict_monotonic": False,
        },
    },

    # ============================ 15m =============================
    "15m": {
        # 趋势更明确；默认提高 min_slope，必要时可开启 strict_monotonic。
        "EMA5MA15": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00028,  # 备选：0.00024（更灵敏）/ 0.00032–0.00036（更稳健）
            "strict_monotonic": False,  # 备选：True（更强趋势确认，减少震荡反手）
        },
        "EMA5MA20": {
            "mode": "linreg",
            "lookback": 4,
            "normalize_by_ema": True,
            "min_slope": 0.00028,  # 与 MA15 基本一致；强趋势取 0.00032
            "strict_monotonic": False,
        },
        "EMA5MA30": {
            "mode": "linreg",
            "lookback": 5,  # 更长 MA 建议 N=5 稍增稳健
            "normalize_by_ema": True,
            "min_slope": 0.00030,
            "strict_monotonic": False,  # 备选：True 在 15m 更适合
        },
        "EMA5MA50": {
            "mode": "linreg",
            "lookback": 5,
            "normalize_by_ema": True,
            "min_slope": 0.00032,  # 备选：0.00035–0.00040 对超强趋势过滤更好
            "strict_monotonic": False,
        },
    },
}


def get_preset(interval: str, ma_period: int) -> Dict[str, Any]:
    """返回指定周期与 MA 周期的斜率预设（字典）。

    interval: "1m" / "5m" / "15m"
    ma_period: 15 / 20 / 30 / 50
    """
    key = f"EMA5MA{ma_period}"
    try:
        return PRESETS[interval][key]
    except KeyError:
        raise KeyError(f"No preset for interval={interval}, ma={ma_period}.")


def to_jsonc_block(d: Dict[str, Any]) -> str:
    """将预设 dict 转为可直接粘贴到 config.jsonc 的 JSONC 片段（带缩进）。"""
    import json
    # 注意：JSONC 支持注释，但此函数生成的是纯 JSON 片段；注释请参考本文件说明。
    return json.dumps(d, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 示例：打印 1m + EMA5/MA20 的斜率配置片段，便于复制到 config.jsonc
    cfg = get_preset("1m", 20)
    print(to_jsonc_block(cfg))