"""民调支持者画像 — 通用分析界面。

支持任意选举: 每个选举在 data/output/ 下一个子目录, 里面放各家加权 CSV。

运行:
    streamlit run app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.aggregate import combine, pollster_support  # noqa: E402
from src.crosstab import support_rate, demographic_pyramid  # noqa: E402
from src.wiki_fetch import fetch as wiki_fetch  # noqa: E402
from src.llm_extract import extract_crosstab, records_from_crosstab, fetch_article_text  # noqa: E402
from src.bias import party_bias_history, history_table, house_effect, adjust_by_party_bias, pollster_rating, margin_of_error, CANDIDATE_PARTY  # noqa: E402

st.set_page_config(page_title="民调支持者画像", layout="wide")
st.title("民调支持者画像分析")

OUTPUT_DIR = ROOT / "data" / "output"

CFG_KEY = "poll_llm_cfg"


def load_llm_config() -> dict:
    """按可靠性读取 LLM 配置: Streamlit Secrets > 浏览器 localStorage。"""
    cfg: dict = {}
    # 1) Streamlit Secrets (云端最可靠, 重启不丢)
    try:
        if "llm" in st.secrets:
            cfg.update(dict(st.secrets["llm"]))
    except Exception:
        pass
    # 2) 浏览器 localStorage (尽力而为; 首次渲染 JS 返回空串, 不会卡住)
    try:
        raw = st_javascript(f"localStorage.getItem('{CFG_KEY}') || ''")
        if raw and raw not in ("null", "", None):
            cfg.update(json.loads(raw))
    except Exception:
        pass
    return cfg


def save_llm_config_to_browser(cfg: dict) -> None:
    payload = json.dumps(json.dumps(cfg, ensure_ascii=False))
    st_javascript(f"localStorage.setItem('{CFG_KEY}', {payload}); ''")


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


UPLOAD_COLS = ["pollster", "survey_date", "method", "age_bin", "gender", "region", "education", "party", "n", "weighted_n"]


def normalize_uploaded(df: pd.DataFrame) -> pd.DataFrame:
    """把用户上传的 CSV 规范化成统一 schema, 宽容处理缺列。

    必填: party 列 + (n 或 weighted_n 之一)。
    缺列自动填默认值 (unknown / 占位日期)。
    """
    if "party" not in df.columns:
        raise ValueError("CSV 缺少必要列 'party' (候选人/政党)")
    if "n" not in df.columns and "weighted_n" not in df.columns:
        raise ValueError("CSV 需要 'n' 或 'weighted_n' 列 (人数)")

    def get(col: str, default: str) -> pd.Series:
        if col in df.columns:
            return df[col].fillna(default).astype(str)
        return pd.Series(default, index=df.index)

    out = pd.DataFrame(index=df.index)
    out["pollster"] = get("pollster", "上传数据")
    out["survey_date"] = get("survey_date", "2026-01-01")
    out["method"] = get("method", "unknown")
    out["age_bin"] = get("age_bin", "unknown")
    out["gender"] = get("gender", "unknown")
    out["region"] = get("region", "unknown")
    out["education"] = get("education", "unknown")
    out["party"] = df["party"].fillna("unknown").astype(str)

    if "n" in df.columns:
        out["n"] = pd.to_numeric(df["n"], errors="coerce").fillna(0)
        out["weighted_n"] = out["n"] if "weighted_n" not in df.columns else pd.to_numeric(df["weighted_n"], errors="coerce").fillna(0)
    else:
        out["weighted_n"] = pd.to_numeric(df["weighted_n"], errors="coerce").fillna(0)
        out["n"] = out["weighted_n"]
    return out[UPLOAD_COLS]


# ---- 侧边栏: 上传 + 选选举 ----
with st.sidebar:
    st.header("上传你的数据")
    uploaded_file = st.file_uploader(
        "上传民调 CSV",
        type="csv",
        help="必填列: party(候选人) + n或weighted_n(人数)。建议: survey_date(YYYY-MM-DD)、pollster(机构)。可选: age_bin/gender/region/education。",
    )

    st.header("从维基百科抓取")
    wiki_query = st.text_input(
        "选举词条名或网址",
        placeholder="如: 2026年台北市市长选举",
    )
    if st.button("抓取民调"):
        if not wiki_query.strip():
            st.warning("请输入选举词条名")
        else:
            try:
                st.session_state["wiki_records"] = wiki_fetch(wiki_query)
                st.session_state["wiki_query"] = wiki_query.strip()
                st.success(f"抓到 {len(st.session_state['wiki_records'])} 行")
            except Exception as e:
                st.error(f"抓取失败: {e}")
    wiki_records = st.session_state.get("wiki_records")

    st.header("LLM 提取交叉表")
    with st.expander("展开 (从新闻正文提取年龄/性别)", expanded=False):
        # 读取配置: Secrets > 浏览器 localStorage
        if "saved_cfg" not in st.session_state:
            st.session_state["saved_cfg"] = load_llm_config()
        saved_cfg = st.session_state["saved_cfg"]

        # 用 setdefault 给 widget key 种初值, 避免 value/key 冲突
        for k, field in [
            ("api_key", "api_key"),
            ("llm_base", "base_url"),
            ("llm_model", "model"),
        ]:
            if k not in st.session_state:
                st.session_state[k] = saved_cfg.get(field, {"llm_base": "https://api.deepseek.com", "llm_model": "deepseek-chat"}.get(k, ""))

        try:
            from_streamlit_secrets = bool(st.secrets.get("llm", {}).get("api_key"))
        except Exception:
            from_streamlit_secrets = False
        if from_streamlit_secrets:
            st.caption("API Key 来自 Streamlit Secrets (云端持久)。")

        api_key = st.text_input("API Key", type="password", key="api_key")
        base_url = st.text_input("Base URL", key="llm_base")
        model = st.text_input("模型", key="llm_model")

        c1, c2 = st.columns([1, 1])
        if c1.button("保存配置到本浏览器"):
            cfg_to_save = {
                "api_key": st.session_state["api_key"].strip(),
                "base_url": st.session_state["llm_base"].strip(),
                "model": st.session_state["llm_model"].strip(),
            }
            save_llm_config_to_browser(cfg_to_save)
            st.session_state["saved_cfg"] = cfg_to_save
            st.success("已存到本浏览器。若同时设了 Secrets, 以 Secrets 为准。")
        if c2.button("清除浏览器配置"):
            st_javascript(f"localStorage.removeItem('{CFG_KEY}'); ''")
            st.session_state["saved_cfg"] = {}
            for k in ["api_key", "llm_base", "llm_model"]:
                st.session_state.pop(k, None)
            st.rerun()
        news_url = st.text_input(
            "新闻网址 (留空则用下面粘贴的文字)",
            key="llm_url",
            placeholder="https://news.tvbs.com.tw/...",
        )
        news_text = st.text_area(
            "粘贴新闻正文 (留空则自动抓上面网址)",
            height=150,
            key="llm_text",
            help="把包含年龄/性别/教育/地区交叉表的新闻文字粘进来。",
        )
        if st.button("提取交叉表"):
            if not api_key:
                st.warning("需要 API Key")
            else:
                source_text = news_text.strip()
                if not source_text and news_url.strip():
                    try:
                        with st.spinner("抓取新闻正文..."):
                            source_text = fetch_article_text(news_url.strip())
                        st.success(f"已抓取正文 {len(source_text)} 字")
                    except Exception as e:
                        st.error(f"抓取正文失败: {e}")
                if not source_text:
                    st.warning("需要新闻正文或网址")
                else:
                    try:
                        data = extract_crosstab(source_text, api_key, base_url, model)
                        st.session_state["llm_records"] = records_from_crosstab(data)
                        st.success(f"提取到 {len(st.session_state['llm_records'])} 行")
                    except Exception as e:
                        st.error(f"提取失败: {e}")
    llm_records = st.session_state.get("llm_records")

    st.header("选择选举")
    elections = list_elections()

    uploaded_records = None
    if uploaded_file is not None:
        try:
            if st.session_state.get("up_key") != uploaded_file.name:
                st.session_state["up_records"] = normalize_uploaded(pd.read_csv(uploaded_file))
                st.session_state["up_key"] = uploaded_file.name
            uploaded_records = st.session_state["up_records"]
            st.success(f"已加载 {uploaded_file.name} ({len(uploaded_records)} 行)")
        except Exception as e:
            st.error(f"上传文件解析失败: {e}")

    if not elections and uploaded_records is None and wiki_records is None and llm_records is None:
        st.warning("还没有数据。可上传 CSV, 输入选举词条从维基百科抓取, 或用 LLM 提取新闻交叉表。")
        st.stop()

    options = elections.copy()
    if llm_records is not None:
        options.insert(0, "LLM 提取的数据")
    if wiki_records is not None:
        options.insert(0, f"维基抓取: {st.session_state.get('wiki_query', '')}")
    if uploaded_records is not None:
        options.insert(0, "上传的数据")

    election = st.selectbox("选举", options)

    if election == "上传的数据":
        records = uploaded_records
    elif election.startswith("维基抓取:"):
        records = wiki_records
    elif election == "LLM 提取的数据":
        records = llm_records
    else:
        records = load_election(election)

    if records is None or records.empty:
        st.error(f"选举 {election} 下没有数据。")
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

# ---- 偏好伪装偏差 ----
st.subheader("偏好伪装偏差 (Preference Falsification)")
st.caption("历史封关民调 vs 实际结果。正值 = 该阵营支持被民调低估 (害羞支持者 / 偏好伪装)。")
st.dataframe(history_table().round(2), use_container_width=True)

st.markdown("**多届平均阵营偏差** (供当前选举外推):")
party_bias = party_bias_history()
st.dataframe(
    pd.DataFrame([{"阵营": k, "平均偏差": f"{v:+.2f}%"} for k, v in party_bias.items()]),
    use_container_width=True,
)

# 机构效应
st.subheader("机构效应 (House Effect)")
st.caption("每家机构相对全体平均的偏差, 正值 = 该机构偏蓝 (对蒋万安高估)。")
st.dataframe(house_effect(sub), use_container_width=True)

# 应用到当前
adjusted_rows = []
for cand in parties:
    rate = merged[merged["party"] == cand]["weighted_n"].sum() / total * 100
    if CANDIDATE_PARTY.get(cand) is None:
        continue
    adj = adjust_by_party_bias({cand: rate})[cand]
    adjusted_rows.append(
        {
            "候选人": cand,
            "民调支持率": f"{rate:.1f}%",
            "调整后预测": f"{adj:.1f}%",
        }
    )
if adjusted_rows:
    st.markdown("应用到当前选举 (民调 + 多届平均偏差):")
    st.dataframe(pd.DataFrame(adjusted_rows), use_container_width=True)
else:
    st.caption("当前候选人不在此历史阵营映射中, 无法自动应用偏差。")

# 机构评级
st.subheader("机构评级 (Pollster Rating)")
st.caption("基于 2024 总统封关民调 vs 实际结果, 平均绝对误差越小越准。A<2%, B<4%, C≥4%。")
st.dataframe(pollster_rating(), use_container_width=True)

# 抽样误差
st.subheader("抽样误差 (Margin of Error)")
st.caption("按当前数据里的样本量 n 估算 (95% 信心水准, z=1.96)。")
moe_rows = []
for c in parties[:5]:
    rate = merged[merged["party"] == c]["weighted_n"].sum() / total * 100
    # 从原始 records 里取该候选人各机构样本量
    sub_c = records[records["party"] == c]
    ns = pd.to_numeric(sub_c["n"], errors="coerce").dropna()
    ns = ns[ns > 0]
    if len(ns) == 0:
        continue
    n = ns.mean()
    moe = margin_of_error(rate, n)
    if moe is None:
        continue
    moe_rows.append(
        {
            "候选人": c,
            "支持率": f"{rate:.1f}%",
            "平均样本量": f"{n:.0f}",
            "抽样误差": f"±{moe}%",
            "区间": f"{max(0, rate - moe):.1f}% ~ {min(100, rate + moe):.1f}%",
        }
    )
if moe_rows:
    st.dataframe(pd.DataFrame(moe_rows), use_container_width=True)
else:
    st.caption("当前数据源没有样本量 (n) 字段, 无法估算抽样误差。上传含 n 列的 CSV 即可看到。")

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
