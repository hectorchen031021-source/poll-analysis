import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.weight import rake, apply_weights  # noqa: E402


def _sample() -> pd.DataFrame:
    """年龄×性别 完全均衡的样本 (每格 100 人)。"""
    rows = []
    for age in ["18-29", "30-44", "45-64", "65+"]:
        for g in ["male", "female"]:
            rows.append({"age_bin": age, "gender": g, "party": "A", "n": 100})
    return pd.DataFrame(rows)


def test_rake_converges_to_targets():
    targets = {
        "age_bin": {"18-29": 0.10, "30-44": 0.20, "45-64": 0.30, "65+": 0.40},
        "gender": {"male": 0.40, "female": 0.60},
    }
    records = _sample()
    w = rake(records, targets)

    weighted = apply_weights(records, w)
    total = weighted["weighted_n"].sum()

    for dim, target in targets.items():
        got = (
            weighted.groupby(dim)["weighted_n"].sum() / total
        )
        for cat, tgt in target.items():
            assert got[cat] == pytest.approx(tgt, abs=1e-4), (dim, cat, got[cat], tgt)


def test_rake_preserves_non_target_dimensions():
    """raking 只缩放目标维度, 不应改变无关信息的总量。"""
    targets = {"gender": {"male": 0.5, "female": 0.5}}
    records = _sample()
    w = rake(records, targets)
    assert np.allclose(w.values, 1.0)  # 原本已均衡, 权重应为 1
