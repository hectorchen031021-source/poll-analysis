"""分析入口: 从加权计数表切支持率。

用法:
    python scripts/analyze/crosstab.py --pollster pollco --party PartyA
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.crosstab import support_rate, demographic_pyramid  # noqa: E402


def main(pollster: str, party: str) -> None:
    import pandas as pd

    path = ROOT / "data" / "output" / f"{pollster}_weighted.csv"
    records = pd.read_csv(path)

    print("按年龄段支持率:")
    print(support_rate(records, by=["age_bin"], party=party).to_string(index=False))
    print()
    print("性别 × 年龄段人口金字塔:")
    print(demographic_pyramid(records, party=party).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pollster", default="pollco")
    parser.add_argument("--party", default="PartyA")
    args = parser.parse_args()
    main(args.pollster, args.party)
