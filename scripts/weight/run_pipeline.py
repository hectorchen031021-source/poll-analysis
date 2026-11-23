"""加权流水线: 归一化 → raking → 写出 weighted 计数表。

用法:
    python scripts/weight/run_pipeline.py --pollster pollco
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.normalize import load_raw, normalize  # noqa: E402
from src.weight import rake, apply_weights  # noqa: E402


# 人口普查基准: 各维度目标比例 (示例值, 替换为真实普查数据)
TARGETS = {
    "age_bin": {"18-29": 0.20, "30-44": 0.26, "45-64": 0.34, "65+": 0.20},
    "gender": {"male": 0.49, "female": 0.51},
}


def main(pollster: str) -> None:
    raw = load_raw(pollster)
    records = normalize(raw, pollster)

    weights = rake(records, TARGETS)
    weighted = apply_weights(records, weights)

    out_dir = ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pollster}_weighted.csv"
    weighted.to_csv(out_path, index=False)

    print(f"记录数: {len(weighted)}")
    print(f"权重范围: {weights.min():.3f} ~ {weights.max():.3f}")
    print(f"写出: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pollster", default="pollco")
    args = parser.parse_args()
    main(args.pollster)
