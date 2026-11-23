"""生成台北市长选举演示数据 (假数据, 仅供演示界面功能)。

警告: 这些数字是编造的, 不代表任何真实民调。真实分析需自行收集数据。

运行:
    python scripts/weight/make_taipei_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.weight import rake, apply_weights  # noqa: E402

AGE = ["20-29", "30-39", "40-49", "50-59", "60-69", "70+"]
GENDER = ["male", "female"]
CANDIDATES = ["蒋万安", "民进党候选人", "民众党候选人", "未决定"]

# 各候选人在时间点 t=0/1/2 的基础支持率 (%)
BASE = {
    "蒋万安": [40, 43, 45],
    "民进党候选人": [26, 25, 24],
    "民众党候选人": [21, 20, 19],
    "未决定": [13, 12, 12],
}

# 年龄修正 (相对基础, 百分点)
AGE_EFFECT = {
    "蒋万安": {"20-29": -12, "30-39": -6, "40-49": 0, "50-59": 6, "60-69": 10, "70+": 14},
    "民进党候选人": {"20-29": 6, "30-39": 4, "40-49": 2, "50-59": 0, "60-69": -4, "70+": -8},
    "民众党候选人": {"20-29": 12, "30-39": 8, "40-49": 4, "50-59": 0, "60-69": -8, "70+": -16},
    "未决定": {"20-29": 0, "30-39": 0, "40-49": 0, "50-59": 0, "60-69": 0, "70+": 0},
}

# 性别修正
GENDER_EFFECT = {
    "蒋万安": {"male": 2, "female": -2},
    "民进党候选人": {"male": -2, "female": 2},
    "民众党候选人": {"male": 2, "female": -2},
    "未决定": {"male": 0, "female": 0},
}

# 机构偏差 (体现"机构效应")
POLLSTERS = {
    "TVBS": {"bias": {"蒋万安": 3, "民进党候选人": -2, "民众党候选人": -1, "未决定": 0}, "n": 1500},
    "美丽岛电子报": {"bias": {"蒋万安": 0, "民进党候选人": 0, "民众党候选人": 0, "未决定": 0}, "n": 1200},
    "台湾民意基金会": {"bias": {"蒋万安": -3, "民进党候选人": 2, "民众党候选人": -1, "未决定": 2}, "n": 1100},
}

DATES = ["2026-08-05", "2026-09-20", "2026-11-05"]

# 人口普查基准 (台北, 示例值)
TARGETS = {
    "age_bin": {"20-29": 0.16, "30-39": 0.17, "40-49": 0.19, "50-59": 0.18, "60-69": 0.17, "70+": 0.13},
    "gender": {"male": 0.48, "female": 0.52},
}


def _prob(cand: str, age: str, gender: str, t: int, bias: dict[str, float]) -> float:
    return max(BASE[cand][t] + AGE_EFFECT[cand][age] + GENDER_EFFECT[cand][gender] + bias[cand], 1.0)


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for name, meta in POLLSTERS.items():
        for t, date in enumerate(DATES):
            for age in AGE:
                for gender in GENDER:
                    ps = np.array([_prob(c, age, gender, t, meta["bias"]) for c in CANDIDATES])
                    ps = ps / ps.sum()
                    # 年龄×性别 cell 样本量 (按人口比例, 加噪声)
                    cell_n = int(meta["n"] / (len(AGE) * len(GENDER)) * rng.uniform(0.85, 1.15))
                    counts = rng.multinomial(cell_n, ps)
                    for c, cnt in zip(CANDIDATES, counts):
                        rows.append(
                            {
                                "pollster": name,
                                "survey_date": date,
                                "method": "CATI",
                                "age_bin": age,
                                "gender": gender,
                                "region": "unknown",
                                "education": "unknown",
                                "party": c,
                                "n": cnt,
                                "weighted_n": float(cnt),
                            }
                        )
    return pd.DataFrame(rows)


def main() -> None:
    records = generate()
    out_dir = ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in POLLSTERS:
        sub = records[records["pollster"] == name].copy()
        w = rake(sub, TARGETS)
        sub = apply_weights(sub, w)
        sub.to_csv(out_dir / f"{name}_weighted.csv", index=False)
        print(f"{name}: {len(sub)} 行 -> {out_dir / f'{name}_weighted.csv'}")

    print("演示数据生成完毕 (假数据, 仅供演示)。")


if __name__ == "__main__":
    main()
