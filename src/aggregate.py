"""多机构民调合并。

方法: 样本量加权 + 可选时间衰减。

基本思路:
  1. 每家机构算出加权后的计数表 (weighted_n)
  2. 合并时按时间衰减缩放 (越新权重越大)
  3. 跨机构把同一 (维度 × 政党) 的加权计数相加
  4. 从合并计数重新算支持率

不做 MRP/贝叶斯, 这是"简单加权平均"版本, 足够做初步推测。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DIMS = ["age_bin", "gender", "region", "education", "party"]


def time_decay(
    dates: pd.Series,
    reference_date: str | pd.Timestamp,
    half_life_days: float | None = None,
) -> pd.Series:
    """时间衰减权重: 距离 reference_date 越近, 权重越大。

    half_life_days=None 表示不做衰减 (权重全为 1)。
    """
    if half_life_days is None:
        return pd.Series(1.0, index=dates.index)
    days = (pd.to_datetime(reference_date) - pd.to_datetime(dates)).dt.days
    return np.exp(-np.log(2.0) * days / half_life_days)


def combine(
    records: pd.DataFrame,
    reference_date: str | pd.Timestamp,
    half_life_days: float | None = None,
) -> pd.DataFrame:
    """合并多家机构 (records 已含 pollster / survey_date 列)。

    返回合并后的计数表, 只含 DIMS 维度 + weighted_n。
    """
    out = records.copy()
    out["decay"] = time_decay(
        out["survey_date"], reference_date, half_life_days
    )
    out["weighted_n"] = out["weighted_n"] * out["decay"]

    grouped = out.groupby(DIMS, dropna=False)["weighted_n"].sum().reset_index()
    return grouped


def pollster_support(
    records: pd.DataFrame,
    party: str,
) -> pd.DataFrame:
    """每家机构 × 日期 的支持率, 用于对比和趋势。"""
    g = records.groupby(["pollster", "survey_date", "party"])["weighted_n"].sum()
    total = records.groupby(["pollster", "survey_date"])["weighted_n"].sum()
    wide = g.unstack("party", fill_value=0.0)
    result = wide.div(total, axis=0)[party].rename("support_rate").reset_index()
    return result
