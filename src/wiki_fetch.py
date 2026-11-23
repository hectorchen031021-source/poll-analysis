"""通用维基百科民调表抓取。

输入一个选举词条名 (或 URL), 自动:
  1. 搜索维基百科找到页面
  2. 抓取页面里的「民调汇总表」
  3. 解析成统一 schema (每家机构、每个日期、每个候选人一行)

只依赖维基百科页面里的结构化表格, 拿到的是「全体支持率」,
不含年龄/性别交叉表。
"""

from __future__ import annotations

import io
import re
from urllib.parse import quote, unquote

import pandas as pd
import requests

WIKI = "https://zh.wikipedia.org"
ASSUMED_N = 1000

# 列名分类关键字 (简繁通吃)
POLLSTER_KEYS = ["來源", "来源", "機構", "机构", "民調", "民调", "單位", "单位", "委託", "委托", "媒體", "媒体", "報紙", "报纸", "受訪單位", "受访单位"]
DATE_KEYS = ["日期", "時間", "时间"]
SAMPLE_KEYS = ["樣本", "样本", "受訪", "受访", "有效"]
ERROR_KEYS = ["誤差", "误差"]
OTHER_KEYS = ["其他", "未表態", "未表态", "未決定", "未决定", "無意見", "无意见", "不知道", "廢票", "废票", "都不", "未明確", "未明确", "未定"]

UPLOAD_COLS = ["pollster", "survey_date", "method", "age_bin", "gender", "region", "education", "party", "n", "weighted_n"]

UA = {"User-Agent": "poll-analysis/1.0 (educational use)"}


def search(query: str) -> str:
    """用 opensearch 找最匹配的词条标题。"""
    url = f"{WIKI}/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "format": "json",
    }
    r = requests.get(url, params=params, headers=UA, timeout=20)
    r.raise_for_status()
    data = r.json()
    titles = data[1] if len(data) > 1 else []
    if not titles:
        raise ValueError(f"维基百科找不到「{query}」")
    return titles[0]


def _title_from_query(query: str) -> str:
    q = query.strip()
    if q.startswith("http"):
        # 从 URL 提取标题
        m = re.search(r"/wiki/([^#?]+)", q)
        if m:
            return unquote(m.group(1))
    return q


def fetch_html(title: str) -> str:
    url = f"{WIKI}/wiki/{quote(title)}"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def _is_type(colname: str, keys: list[str]) -> bool:
    return any(k in colname for k in keys)


def _pct(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    s = str(val).replace("%", "").replace("−", "-").replace("＋", "+").strip()
    if s in ("", "-", "–", "—", "–", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(text) -> str | None:
    if text is None:
        return None
    t = str(text).strip()
    if not t or "辯論" in t or "辩论" in t or "政見" in t or "政见" in t:
        return None
    year = 2026
    m = re.search(r"(\d{4})年", t)
    if m:
        year = int(m.group(1))
    months = re.findall(r"(\d{1,2})月", t)
    days = re.findall(r"(\d{1,2})日", t)
    if not months or not days:
        return None
    return f"{year}-{int(months[-1]):02d}-{int(days[-1]):02d}"


def parse_poll_table(html: str) -> pd.DataFrame:
    """在页面 HTML 里找民调表并解析成统一 schema。"""
    tables = pd.read_html(io.StringIO(html))
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        # 找含日期列 + 至少 3 个数值列的表格
        date_col = next((c for c in cols if _is_type(c, DATE_KEYS)), None)
        if date_col is None:
            continue
        result = _parse_table(tbl, cols, date_col)
        if result is not None and not result.empty:
            return result
    raise RuntimeError("页面上找不到可解析的民调表")


def _parse_table(tbl: pd.DataFrame, cols: list[str], date_col: str) -> pd.DataFrame | None:
    pollster_col = next((c for c in cols if _is_type(c, POLLSTER_KEYS)), None)
    other_cols = [c for c in cols if _is_type(c, OTHER_KEYS)]
    skip = {date_col}
    if pollster_col:
        skip.add(pollster_col)
    skip |= {c for c in cols if _is_type(c, SAMPLE_KEYS) or _is_type(c, ERROR_KEYS)}
    cand_cols = [c for c in cols if c not in skip and c not in other_cols and c != "Unnamed: 0"]

    rows = []
    prev_pollster = None
    for _, row in tbl.iterrows():
        date = _parse_date(row.get(date_col))
        if date is None:
            continue
        pollster = str(row.get(pollster_col, "")).strip() if pollster_col else ""
        pollster = re.sub(r"\[[^\]]*\]", "", pollster).strip()
        if not pollster or pollster == "nan":
            if prev_pollster:
                pollster = prev_pollster
            else:
                continue
        prev_pollster = pollster

        for c in cand_cols:
            v = _pct(row.get(c))
            if v is None:
                continue
            rows.append(_record(pollster, date, _clean_name(c), v))

        other = sum((_pct(row.get(c)) or 0.0) for c in other_cols)
        if other > 0:
            rows.append(_record(pollster, date, "其他/未表态", other))

    if not rows:
        return None
    return pd.DataFrame(rows)


def _clean_name(colname: str) -> str:
    # '國民 蔣萬安' -> 保留全名; 去引用标记
    return re.sub(r"\[[^\]]*\]", "", colname).strip()


def _record(pollster: str, date: str, party: str, pct: float) -> dict:
    n = round(pct / 100 * ASSUMED_N)
    return {
        "pollster": pollster,
        "survey_date": date,
        "method": "unknown",
        "age_bin": "unknown",
        "gender": "unknown",
        "region": "unknown",
        "education": "unknown",
        "party": party,
        "n": n,
        "weighted_n": n,
    }


def fetch(query: str) -> pd.DataFrame:
    """入口: 词条名或 URL -> 统一 schema DataFrame。"""
    title = _title_from_query(query)
    html = fetch_html(title)
    return parse_poll_table(html)
