"""支持率时间趋势。

输入含 survey_date 的加权计数表, 输出某政党支持率随时间的变化。
"""

from __future__ import annotations

import pandas as pd


def trend(
    records: pd.DataFrame,
    party: str,
    by: list[str] | None = None,
) -> pd.DataFrame:
    """按日期(可选再按维度)算某政党支持率。

    参数:
        records: 统一 schema 计数表, 含 survey_date。
        party: 目标政党/候选人。
        by: 额外分组维度, 如 ["age_bin"] 看某年龄段的趋势。
    """
    group_cols = (by or []) + ["party"]
    g = records.groupby(["survey_date"] + group_cols)["weighted_n"].sum()
    total = records.groupby(["survey_date"] + (by or []))["weighted_n"].sum()

    wide = g.unstack("party", fill_value=0.0)
    result = wide.div(total, axis=0)[party].rename("support_rate").reset_index()
    result["survey_date"] = pd.to_datetime(result["survey_date"])
    return result.sort_values("survey_date")


def moving_average(
    series: pd.Series,
    window: int = 3,
) -> pd.Series:
    """简单移动平均, 平滑噪声。"""
    return series.rolling(window, min_periods=1).mean()
