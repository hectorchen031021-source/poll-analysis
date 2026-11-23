"""归一化: 把各家原始数据映射到统一 schema。

每家机构的字段命名、年龄段切分、性别编码都不同。
为每个机构写一个 mapper, 输出统一的 PollRecord 行。

下方 pollco 是完整示例, 可直接运行:
    python -c "from src.normalize import normalize; print(normalize(None, 'pollco'))"
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

AGE_BINS = ["18-29", "30-44", "45-64", "65+"]

COLS = [
    "pollster",
    "survey_date",
    "method",
    "age_bin",
    "gender",
    "region",
    "education",
    "party",
    "n",
    "weighted_n",
]

# ---- 各机构映射规则 ----

AGE_MAP: dict[str, dict[str, str]] = {
    # 示例机构 PollCo: 6 档 → 统一 4 档
    "pollco": {
        "18-24": "18-29",
        "25-34": "18-29",
        "35-44": "30-44",
        "45-54": "45-64",
        "55-64": "45-64",
        "65+": "65+",
    },
}

GENDER_MAP: dict[str, dict[str, str]] = {
    "pollco": {"Male": "male", "Female": "female", "Other": "other"},
}

METHOD_MAP: dict[str, str] = {
    "pollco": "online",
}


def _map_age(pollster: str, label: str) -> str:
    m = AGE_MAP.get(pollster)
    if m is None:
        raise KeyError(f"机构 {pollster} 无年龄段映射, 请在 AGE_MAP 中补充")
    for raw, std in m.items():
        if raw in label:
            return std
    raise ValueError(f"未知年龄段 {label!r} (机构 {pollster})")


def normalize_pollco(df: pd.DataFrame) -> pd.DataFrame:
    """PollCo 原始格式示例:

        age,gender,candidate,count
        18-24,Male,PartyA,120
        18-24,Female,PartyA,110
        ...

    长格式计数表 → 统一 schema。
    """
    out = pd.DataFrame()
    out["pollster"] = "pollco"
    out["survey_date"] = df.get("survey_date", "2026-11-01")
    out["method"] = METHOD_MAP["pollco"]
    out["age_bin"] = df["age"].map(lambda x: _map_age("pollco", x))
    out["gender"] = df["gender"].map(GENDER_MAP["pollco"])
    out["region"] = df.get("region", "unknown")
    out["education"] = df.get("education", "unknown")
    out["party"] = df["candidate"]
    out["n"] = df["count"]
    out["weighted_n"] = df["count"]  # 未加权, 初始等于 n
    return out[COLS]


NORMALIZERS = {
    "pollco": normalize_pollco,
}


def normalize(df: pd.DataFrame, pollster: str) -> pd.DataFrame:
    """把单个机构的原始 DataFrame 转为统一 schema。"""
    fn = NORMALIZERS.get(pollster)
    if fn is None:
        raise KeyError(
            f"机构 {pollster} 无归一化器。在 NORMALIZERS 中注册, "
            f"并参考 normalize_pollco 编写。"
        )
    return validate(fn(df))


def validate(
    records: pd.DataFrame,
    allowed_age_bins: set[str] | None = None,
) -> pd.DataFrame:
    """校验归一化结果是否符合 schema。

    allowed_age_bins: 允许的年龄段集合。None 时不校验具体取值,
    以便支持不同选举场景的年龄切分 (如台湾常用的 20-29/30-39/...)。
    """
    missing = set(COLS) - set(records.columns)
    if missing:
        raise ValueError(f"缺少列: {missing}")
    if not records["n"].ge(0).all():
        raise ValueError("存在负计数")
    if records["age_bin"].isna().any() or (records["age_bin"] == "").any():
        raise ValueError("存在空年龄段")
    if allowed_age_bins is not None:
        bad_age = set(records["age_bin"]) - set(allowed_age_bins)
        if bad_age:
            raise ValueError(f"非法年龄段: {bad_age}")
    return records


def load_raw(pollster: str, path: str | Path | None = None) -> pd.DataFrame:
    """读取某机构原始数据。默认从 data/raw/{pollster}.csv 读。"""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "raw" / f"{pollster}.csv"
    return pd.read_csv(path)
