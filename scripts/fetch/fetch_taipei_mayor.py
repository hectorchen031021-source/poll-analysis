"""抓取維基百科 2026 台北市長選舉民調表, 轉成統一 schema。

資料來源: 維基百科「2026年臺北市市長選舉」頁面的民調表。
維基只提供全體支持率 (無年齡/性別交叉表), 故人口維度填 unknown。

運行:
    python scripts/fetch/fetch_taipei_mayor.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

URL = "https://zh.wikipedia.org/wiki/2026年臺北市市長選舉"
ELECTION = "taipei_mayor_2026"

MAIN_CANDIDATES = ["蔣萬安", "沈伯洋"]
MINOR_CANDIDATES = ["郭璽", "唐新民", "蕭文乾", "林志成", "其他/未表態"]
ASSUMED_N = 1000  # 維基無樣本量, 用百分比×1000 反推計數 (比例不變)


def parse_date(text: str) -> str | None:
    """把 '2026年5月4日至5日' / '5月21日至26日' / '10月14至16日' 轉成 ISO 日期。

    取最後出現的「月」與最後出現的「日」作為調查結束日。
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t or "辯論" in t or "政見" in t:
        return None  # 事件標記, 非民調行

    year = 2026
    m = re.search(r"(\d{4})年", t)
    if m:
        year = int(m.group(1))

    months = re.findall(r"(\d{1,2})月", t)
    days = re.findall(r"(\d{1,2})日", t)
    if not months or not days:
        return None
    end_month, end_day = int(months[-1]), int(days[-1])
    return f"{year}-{end_month:02d}-{end_day:02d}"


def fetch_poll_table() -> pd.DataFrame:
    headers = {"User-Agent": "poll-analysis/1.0 (educational use)"}
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        joined = " ".join(cols)
        if "調查日期" in joined and "蔣萬安" in joined and "沈伯洋" in joined:
            return tbl
    raise RuntimeError("找不到民調表")


def _col(tbl: pd.DataFrame, keyword: str):
    """按关键字 (候选人名) 找列, 兼容 '國民 蔣萬安' 这类带党派前缀的列名。"""
    for c in tbl.columns:
        if keyword in str(c):
            return c
    return None


def main() -> None:
    tbl = fetch_poll_table()
    rows = []

    # 建立候选人名 → 实际列名 的映射
    cand_cols = {cand: _col(tbl, cand) for cand in MAIN_CANDIDATES + MINOR_CANDIDATES}
    pollster_col = _col(tbl, "民調來源") or _col(tbl, "民調")
    date_col = _col(tbl, "調查日期")

    prev_pollster = None
    for _, row in tbl.iterrows():
        pollster = str(row.get(pollster_col, "")).strip()
        pollster = re.sub(r"\[[^\]]*\]", "", pollster).strip()  # 去引用標記 [9][a]
        date_text = row.get(date_col, "")
        date = parse_date(date_text)
        if date is None:
            continue
        if not pollster or pollster == "nan":
            # 機構名繼承上一行 (如 ETtoday 連續多期)
            if prev_pollster:
                pollster = prev_pollster
            else:
                continue
        prev_pollster = pollster

        for cand in MAIN_CANDIDATES:
            val = _pct(row.get(cand_cols[cand]))
            if val is None:
                continue
            rows.append(
                {
                    "pollster": pollster,
                    "survey_date": date,
                    "method": "unknown",
                    "age_bin": "unknown",
                    "gender": "unknown",
                    "region": "unknown",
                    "education": "unknown",
                    "party": cand,
                    "n": round(val / 100 * ASSUMED_N),
                    "weighted_n": round(val / 100 * ASSUMED_N),
                }
            )

        # 其他 = 小黨 + 未表態
        other = 0.0
        for cand in MINOR_CANDIDATES:
            v = _pct(row.get(cand_cols[cand]))
            if v is not None:
                other += v
        if other > 0:
            rows.append(
                {
                    "pollster": pollster,
                    "survey_date": date,
                    "method": "unknown",
                    "age_bin": "unknown",
                    "gender": "unknown",
                    "region": "unknown",
                    "education": "unknown",
                    "party": "其他/未表態",
                    "n": round(other / 100 * ASSUMED_N),
                    "weighted_n": round(other / 100 * ASSUMED_N),
                }
            )

    out = pd.DataFrame(rows)
    out_dir = ROOT / "data" / "output" / ELECTION
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "wikipedia_weighted.csv", index=False)
    print(f"抓到 {out['pollster'].nunique()} 家機構, {len(out)} 行")
    print(f"日期範圍: {out['survey_date'].min()} ~ {out['survey_date'].max()}")
    print(f"寫出: {out_dir / 'wikipedia_weighted.csv'}")


def _pct(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    s = str(val).replace("%", "").replace("−", "-").strip()
    if s in ("", "-", "–", "—", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


if __name__ == "__main__":
    main()
