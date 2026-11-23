"""民调支持者画像 — 通用分析界面。

支持任意选举: 每个选举在 data/output/ 下一个子目录, 里面放各家加权 CSV。

运行:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.aggregate import combine, pollster_support  # noqa: E402
from src.crosstab import support_rate, demographic_pyramid  # noqa: E402

st.set_page_config(page_title="民调支持者画像", layout="wide")
st.title("民调支持者画像分析")

OUTPUT_DIR = ROOT / "data" / "output"


@st.cache_data
def list_elections() -> list[str]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir())


@st.cache_data
def load_election(election: str) -> pd.DataFrame:
    frames = []
    folder = OUTPUT_DIR / election
    for f in sorted(folder.glob("*_weighted.csv")):
        frames.append(pd.read_csv(f))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---- 侧边栏: 选选举 ----
with st.sidebar:
    st.header("选择选举")
    elections = list_elections()

    if not elections:
        st.warning("还没有任何选举数据。")
        st.markdown(
            "**如何添加一个选举:**\n\n"
            "1. 在 `data/output/` 下建一个子目录 (如 `my_election/`)\n"
            "2. 把各家机构的加权 CSV 放进去 (`机构名_weighted.csv`)\n"
            "3. 刷新本页\n\n"
            "加权 CSV 可由 `scripts/weight/run_pipeline.py` 生成。"
        )
        st.stop()

    election = st.selectbox("选举", elections)

    records = load_election(election)

    if records.empty:
        st.error(f"选举 {election} 下没有加权结果。")
        st.stop()

    pollsters = sorted(records["pollster"].unique())
    selected = st.multiselect("选择机构", pollsters, default=pollsters)

    st.header("分析设置")
    use_weighted = st.checkbox("使用加权计数", value=True)
    half_life = st.slider(
        "时间衰减半衰期(天, 0=不衰减)",
        min_value=0, max_value=90, value=0, step=5,
        help="合并多家时, 越新的民调权重越大。0 表示不看时间。",
    )

sub = records[records["pollster"].isin(selected)].copy()
if not use_weighted:
    sub["weighted_n"] = sub["n"]

if sub.empty:
    st.stop()

parties = sorted(sub["party"].unique())
party = st.selectbox("目标候选人 / 政党", parties)

ref_date = pd.to_datetime(sub["survey_date"]).max()
half_life_days = half_life if half_life > 0 else None

# ---- 时间趋势 ----
st.subheader(f"{party} 支持率 — 时间趋势")
per = pollster_support(sub, party)
fig = go.Figure()
for name, grp in per.groupby("pollster"):
    grp = grp.sort_values("survey_date")
    fig.add_trace(
        go.Scatter(
            x=pd.to_datetime(grp["survey_date"]),
            y=grp["support_rate"],
            mode="lines+markers",
            name=name,
        )
    )
fig.update_layout(
    yaxis_title="支持率",
    xaxis_title="日期",
    yaxis_tickformat=".0%",
    yaxis_range=[0, 1],
    legend_title="机构",
)
st.plotly_chart(fig, use_container_width=True)

# ---- 合并总支持率 ----
st.subheader("合并后总支持率")
merged = combine(sub, ref_date, half_life_days)
total = merged["weighted_n"].sum()
merged_rate = merged[merged["party"] == party]["weighted_n"].sum() / total

col1, col2, col3 = st.columns(3)
col1.metric(f"{party} 合并支持率", f"{merged_rate:.1%}")
col2.metric("纳入机构数", f"{len(selected)}")
col3.metric("时间衰减", "关" if half_life_days is None else f"{half_life} 天")

st.markdown("合并后各候选人:")
merged_rate_all = merged.groupby("party")["weighted_n"].sum() / total
merged_rate_all = merged_rate_all.sort_values(ascending=False)
st.dataframe(
    merged_rate_all.rename("support_rate").round(4).to_frame().T,
    use_container_width=True,
)

# ---- 支持者画像 ----
has_age = set(sub["age_bin"]) != {"unknown"}
has_gender = set(sub["gender"]) != {"unknown"}

if has_age or has_gender:
    if has_age:
        st.subheader(f"{party} 支持者画像 — 按年龄")
        age_df = support_rate(merged, by=["age_bin"], party=party, weighted=True)
        fig2 = go.Figure(
            go.Bar(
                x=age_df["age_bin"],
                y=age_df["support_rate"],
                marker_color="#1f77b4",
                text=age_df["support_rate"].round(3),
                textposition="outside",
            )
        )
        fig2.update_layout(yaxis_title="支持率", xaxis_title="年龄段", yaxis_range=[0, 1])
        st.plotly_chart(fig2, use_container_width=True)

    if has_age and has_gender:
        st.subheader("性别 × 年龄 人口金字塔")
        pyr = demographic_pyramid(merged, party=party)
        fig3 = go.Figure()
        for gender, color, side in [("male", "#1f77b4", -1), ("female", "#ff7f0e", 1)]:
            psub = pyr[pyr["gender"] == gender]
            fig3.add_trace(
                go.Bar(
                    y=psub["age_bin"],
                    x=side * psub["support_rate"],
                    orientation="h",
                    name=gender,
                    marker_color=color,
                    text=psub["support_rate"].round(3),
                    textposition="outside",
                )
            )
        fig3.update_layout(
            barmode="overlay",
            yaxis_title="年龄段",
            xaxis_title="男性 ← 支持率 → 女性",
        )
        st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("此数据源没有年龄/性别交叉表(如维基百科只汇总全体支持率), 只能看趋势与总支持率。")

# ---- 完整切分表 ----
st.subheader("完整切分表")
dims = st.multiselect(
    "分组维度",
    ["age_bin", "gender", "region", "education"],
    default=["age_bin", "gender"],
)
if dims:
    st.dataframe(support_rate(merged, by=dims, party=party, weighted=True))
