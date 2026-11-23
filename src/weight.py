"""Raking / IPF 加权。

目标: 让样本在多个维度上的边缘分布逼近人口普查基准。
算法: 迭代比例拟合 (Iterative Proportional Fitting)。

  1. 初始权重全为 1
  2. 逐维度缩放, 使该维度边缘分布 = 基准
  3. 循环直到所有维度都收敛
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rake(
    records: pd.DataFrame,
    targets: dict[str, dict[str, float]],
    tol: float = 1e-6,
    max_iter: int = 100,
) -> pd.Series:
    """返回每条记录的权重。

    参数:
        records: 统一 schema 的计数表 (每行一个单元)。
        targets: {维度列名: {类别: 目标比例}}。
                 如 {"age_bin": {"18-29": 0.20, ...},
                     "gender": {"male": 0.49, "female": 0.51}}。
        tol: 收敛阈值。
        max_iter: 最大迭代次数。
    """
    weights = np.ones(len(records))

    for _ in range(max_iter):
        max_delta = 0.0

        for dim, target in targets.items():
            # 当前样本在该维度的加权边缘分布
            sample = (
                pd.Series(weights, index=records[dim])
                .groupby(level=0)
                .sum()
                / weights.sum()
            )

            # 缩放因子 = 目标比例 / 样本比例
            for cat, tgt in target.items():
                if cat not in sample.index:
                    continue
                factor = tgt / max(sample[cat], 1e-12)
                weights[records[dim] == cat] *= factor
                max_delta = max(max_delta, abs(factor - 1.0))

        if max_delta < tol:
            break

    return pd.Series(weights, index=records.index)


def apply_weights(records: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """把权重写回 weighted_n 列。"""
    records = records.copy()
    records["weighted_n"] = records["n"] * weights
    return records
