"""用 LLM 从新闻正文提取民调交叉表 (年龄/性别/教育/地区)。

OpenAI 兼容 API (DeepSeek / GPT / 任何 /chat/completions 端点)。
API key 只经 session_state 传入, 不进代码、不进 git。
"""

from __future__ import annotations

import json
import re

import pandas as pd
import requests

SYSTEM_PROMPT = """你是民调数据提取器。从新闻正文中提取候选人的支持率交叉表。

只输出 JSON, 不要任何其他文字、解释或 markdown 代码块。

JSON 结构:
{
  "pollster": "机构名(如 TVBS, 若文中没有则 null)",
  "survey_date": "调查结束日期 YYYY-MM-DD, 若没有则 null",
  "candidates": ["候选人1", "候选人2"],
  "age": {"20-29": {"候选人1": 33, "候选人2": 54}},
  "gender": {"male": {"候选人1": 46, "候选人2": 46}, "female": {...}},
  "education": {"高中职": {"候选人1": 51, "候选人2": 36}},
  "region": {"松山信义": {"候选人1": 49, "候选人2": 39}}
}

规则:
- 百分比写纯数字, 不带 % 号。
- 文中没提到的维度就省略该键。
- 无法确定的数字不要瞎编, 宁缺勿错。
- 年龄段尽量统一成 20-29 / 30-39 / 40-49 / 50-59 / 60-69 / 70+ 这种格式。
"""


def extract_crosstab(
    text: str,
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
) -> dict:
    """调 LLM, 返回结构化交叉表 dict。"""
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"

    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    # 去掉可能的 markdown 代码块包裹
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 }
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start : end + 1])
        raise


def records_from_crosstab(data: dict) -> pd.DataFrame:
    """把 LLM 返回的 dict 转成统一 schema DataFrame。"""
    candidates = data.get("candidates") or []
    pollster = data.get("pollster") or "LLM提取"
    date = data.get("survey_date") or "2026-01-01"

    dim_map = {
        "age": "age_bin",
        "gender": "gender",
        "education": "education",
        "region": "region",
    }

    rows = []
    for dim, col in dim_map.items():
        groups = data.get(dim)
        if not groups:
            continue
        for group_name, cand_rates in groups.items():
            if not isinstance(cand_rates, dict):
                continue
            for cand, rate in cand_rates.items():
                try:
                    n = round(float(rate) / 100 * 1000)
                except (TypeError, ValueError):
                    continue
                row = {
                    "pollster": pollster,
                    "survey_date": date,
                    "method": "unknown",
                    "age_bin": "unknown",
                    "gender": "unknown",
                    "region": "unknown",
                    "education": "unknown",
                    "party": cand,
                    "n": n,
                    "weighted_n": n,
                }
                row[col] = _norm_group(dim, group_name)
                rows.append(row)

    if not rows:
        raise ValueError("LLM 没有提取到任何交叉表数据")
    return pd.DataFrame(rows)


def _norm_group(dim: str, name: str) -> str:
    name = str(name).strip()
    if dim == "gender":
        return {"男": "male", "男性": "male", "male": "male", "女": "female", "女性": "female", "female": "female"}.get(name, name)
    return name
