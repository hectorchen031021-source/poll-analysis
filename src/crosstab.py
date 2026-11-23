"""交叉表分析: 从加权计数表切出任意维度的支持率。"""

from __future__ import annotations

import pandas as pd


def support_rate(
    records: pd.DataFrame,
    by: list[str],
    party: str,
    weighted: bool = True,
) -> pd.DataFrame:
    """计算指定政党在各人口维度组合下的支持率。

    参数:
        records: 统一 schema 计数表。
        by: 分组维度, 如 ["age_bin", "gender"]。
        party: 目标政党/候选人。
        weighted: 是否用加权计数。
    返回:
        DataFrame, 含各组支持率。
    """
    col = "weighted_n" if weighted else "n"

    grouped = records.groupby(by + ["party"])[col].sum().unstack(fill_value=0)
    total = grouped.sum(axis=1)
    result = (grouped[party] / total).rename("support_rate").reset_index()
    result["weighted"] = weighted
    return result


def demographic_pyramid(records: pd.DataFrame, party: str) -> pd.DataFrame:
    """性别 × 年龄段的人口金字塔 (供 plotly 画图)。"""
    return support_rate(records, by=["gender", "age_bin"], party=party)
