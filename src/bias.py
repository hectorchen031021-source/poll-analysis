"""偏好伪装偏差 (Preference Falsification) 与民调偏差估计。

方法:
  1. 取历史选举的封关民调 (全体口径, 含未表态)
  2. 归一化到「已表态者」口径 (去掉未表态)
  3. 偏差 = 实际得票率 - 归一化民调
     正值 = 民调低估 (支持者害羞 / 偏好伪装)
     负值 = 民调高估

数据来源: 维基百科「2022年臺北市市長選舉」。
"""

from __future__ import annotations

# ---- 2022 台北市长 历史数据 ----
# 封关民调平均 (11月, 全体口径, 含未表态)
POLL_2022 = {"蔣萬安": 33.2, "陳時中": 27.3, "黃珊珊": 22.8}
UNDECIDED_2022 = 16.7
# 实际得票率
RESULT_2022 = {"蔣萬安": 42.29, "陳時中": 31.93, "黃珊珊": 25.14}

# 政党阵营 → 偏差 (由 2022 计算, 供 2026 外推)
# 正值 = 该阵营支持在民调里被低估
PARTY_BIAS = {
    "國民黨": 2.43,
    "民進黨": -0.84,
    "無黨/白": -2.23,
}

# 候选人名 → 阵营 映射 (用于把偏差应用到当前选举)
CANDIDATE_PARTY = {
    "蔣萬安": "國民黨",
    "蒋万安": "國民黨",
    "國民 蔣萬安": "國民黨",
    "沈伯洋": "民進黨",
    "民進 沈伯洋": "民進黨",
    "陳時中": "民進黨",
    "陈时中": "民進黨",
    "黃珊珊": "無黨/白",
    "黄珊珊": "無黨/白",
}


def normalize(poll: dict[str, float], undecided: float) -> dict[str, float]:
    """把含未表态的支持率, 归一化到已表态者口径 (百分比)。"""
    total = 100 - undecided
    if total <= 0:
        return poll
    return {k: round(v / total * 100, 2) for k, v in poll.items()}


def preference_falsification(
    poll: dict[str, float],
    undecided: float,
    result: dict[str, float],
) -> dict[str, float]:
    """算每个候选人的偏好伪装偏差 (结果 - 归一化民调, 百分点)。"""
    norm = normalize(poll, undecided)
    bias = {}
    for cand in result:
        bias[cand] = round(result[cand] - norm.get(cand, 0), 2)
    return bias


def compute_2022_bias() -> dict[str, float]:
    """计算 2022 台北市长的偏好伪装偏差。"""
    return preference_falsification(POLL_2022, UNDECIDED_2022, RESULT_2022)


def adjust_by_party_bias(support: dict[str, float], party_of: dict[str, str]) -> dict[str, float]:
    """用历史政党偏差调整当前支持率 (外推偏好伪装)。

    support: 当前候选人 -> 支持率 (%)
    party_of: 当前候选人 -> 阵营 (國民黨/民進黨/無黨白)
    """
    adjusted = {}
    for cand, rate in support.items():
        party = party_of.get(cand)
        bias = PARTY_BIAS.get(party, 0.0) if party else 0.0
        adjusted[cand] = round(rate + bias, 2)
    return adjusted
