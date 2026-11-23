"""民调偏差分析。

包含:
  1. 偏好伪装偏差 (Preference Falsification) — 历史封关民调 vs 实际结果
  2. 机构效应 (House Effect) — 每家机构相对市场平均的系统性偏差

数据来源: 维基百科历年台北市长选举页面的民调表 + 开票结果。
"""

from __future__ import annotations

import pandas as pd

# ---- 历史选举: 封关民调平均 (全体口径含未表态) 与 实际结果 ----
# 每项: 候选人 -> 封关民调 % ; 实际 -> 候选人 -> 得票率 %
HISTORY = [
    {
        "year": 2022,
        "poll": {"蔣萬安": 33.2, "陳時中": 27.3, "黃珊珊": 22.8},
        "undecided": 16.7,
        "result": {"蔣萬安": 42.29, "陳時中": 31.93, "黃珊珊": 25.14},
        "party": {"蔣萬安": "國民黨", "陳時中": "民進黨", "黃珊珊": "無黨/白"},
    },
    {
        "year": 2018,
        "poll": {"柯文哲": 36.2, "丁守中": 31.9, "姚文智": 10.7},
        "undecided": 21.2,
        "result": {"柯文哲": 41.07, "丁守中": 40.82, "姚文智": 17.28},
        "party": {"柯文哲": "無黨/白", "丁守中": "國民黨", "姚文智": "民進黨"},
    },
]

# 候选人名 → 阵营 (用于把偏差应用到当前选举)
CANDIDATE_PARTY = {
    "蔣萬安": "國民黨", "蒋万安": "國民黨", "國民 蔣萬安": "國民黨",
    "丁守中": "國民黨", "连胜文": "國民黨", "連勝文": "國民黨",
    "沈伯洋": "民進黨", "民進 沈伯洋": "民進黨", "陳時中": "民進黨", "陈时中": "民進黨", "姚文智": "民進黨",
    "黃珊珊": "無黨/白", "黄珊珊": "無黨/白", "柯文哲": "無黨/白",
}


def normalize(poll: dict[str, float], undecided: float) -> dict[str, float]:
    """把含未表态的支持率归一化到已表态口径 (百分比)。"""
    total = 100 - undecided
    if total <= 0:
        return dict(poll)
    return {k: round(v / total * 100, 2) for k, v in poll.items()}


def preference_falsification(
    poll: dict[str, float], undecided: float, result: dict[str, float]
) -> dict[str, float]:
    """单届: 偏好伪装偏差 = 实际得票率 - 归一化封关民调 (百分点)。"""
    norm = normalize(poll, undecided)
    return {c: round(result[c] - norm.get(c, 0), 2) for c in result}


def party_bias_history() -> dict[str, float]:
    """按阵营汇总多届历史, 得到平均偏好伪装偏差。"""
    acc: dict[str, list[float]] = {}
    for entry in HISTORY:
        bias = preference_falsification(entry["poll"], entry["undecided"], entry["result"])
        for cand, b in bias.items():
            party = entry["party"].get(cand)
            if party:
                acc.setdefault(party, []).append(b)
    return {p: round(sum(v) / len(v), 2) for p, v in acc.items()}


def history_table() -> pd.DataFrame:
    """每届的明细表 (封关民调 / 实际 / 偏差), 用于展示。"""
    rows = []
    for entry in HISTORY:
        bias = preference_falsification(entry["poll"], entry["undecided"], entry["result"])
        norm = normalize(entry["poll"], entry["undecided"])
        for cand in entry["result"]:
            rows.append(
                {
                    "届": entry["year"],
                    "候选人": cand,
                    "阵营": entry["party"].get(cand, ""),
                    "封关民调(归一化)": norm.get(cand, 0),
                    "实际得票率": entry["result"][cand],
                    "偏好伪装偏差": bias[cand],
                }
            )
    return pd.DataFrame(rows)


def adjust_by_party_bias(support: dict[str, float]) -> dict[str, float]:
    """用多届平均阵营偏差调整当前支持率。"""
    bias = party_bias_history()
    adjusted = {}
    for cand, rate in support.items():
        party = CANDIDATE_PARTY.get(cand)
        b = bias.get(party, 0.0) if party else 0.0
        adjusted[cand] = round(rate + b, 2)
    return adjusted


def house_effect(
    records: pd.DataFrame,
    candidates: list[str] | None = None,
) -> pd.DataFrame:
    """机构效应: 每家机构对某候选人的支持率 相对 全体机构平均 的偏差。

    records: 统一 schema 计数表 (含 pollster / party / weighted_n)。
    candidates: 关注的候选人; 默认取前几名 (按总计数)。
    """
    if candidates is None:
        total_by_party = records.groupby("party")["weighted_n"].sum().sort_values(ascending=False)
        candidates = list(total_by_party.index[:3])

    rows = []
    for cand in candidates:
        # 每家机构该候选人的支持率
        g = records.groupby(["pollster", "party"])["weighted_n"].sum().unstack(fill_value=0.0)
        tot = g.sum(axis=1)
        rates = g[cand] / tot if cand in g.columns else pd.Series(0.0, index=g.index)
        market = records[records["party"] == cand]["weighted_n"].sum() / records["weighted_n"].sum()
        for pollster, r in rates.items():
            rows.append(
                {
                    "候选人": cand,
                    "机构": pollster,
                    "机构支持率": round(r * 100, 1),
                    "市场平均": round(market * 100, 1),
                    "机构效应": round((r - market) * 100, 1),
                }
            )
    return pd.DataFrame(rows)
