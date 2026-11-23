# Poll Demographic Analyzer

分析多家机构的民调数据,拆解支持者的年龄、性别、地区、教育等人口变量。

## 核心思路

民调分析的本质是**交叉表(crosstab) + 加权(weighting)**:

1. 各家机构原始数据格式不同 → 先归一化成统一 schema
2. 样本有偏差、样本量不同 → 用 raking/IPF 加权对齐人口普查基准
3. 加权后的交叉表 → 任意维度切分(性别×年龄×政党支持率)

## 目录结构

```
poll-analysis/
├── data/
│   ├── raw/            # 原始数据, 按选举分目录
│   └── output/         # 加权结果, 按选举分目录
│       └── {选举名}/   # 每个选举一个子目录
│           └── {机构名}_weighted.csv
├── schema/
│   └── poll_record.json   # 统一数据契约(唯一真源)
├── src/
│   ├── normalize.py    # 归一化到统一 schema
│   ├── weight.py       # raking / IPF 加权
│   ├── aggregate.py    # 多机构合并(样本量+时间衰减)
│   ├── trend.py        # 支持率时间趋势
│   └── crosstab.py     # 交叉表 + 人口金字塔
├── scripts/
│   ├── weight/         # 加权流水线 + demo 生成器
│   └── analyze/        # 分析入口
├── app.py              # Streamlit 通用分析界面
├── notebooks/
└── tests/
```

## 数据流

```
raw/{选举}/ --normalize--> 统一schema --weight(raking)--> output/{选举}/加权计数表
      --aggregate(多机构合并)--> 支持率/趋势/画像
```

## 支持任意选举

项目对选举类型**无假设**。每个选举就是 `data/output/` 下的一个子目录。
台北市长、总统、立委、任何国家的选举都一样——只要数据进了统一 schema,就能分析。

**新增一个选举:**
1. 在 `data/output/` 下建子目录,如 `presidential_2028/`
2. 把各家机构的加权 CSV 放进去(`机构名_weighted.csv`)
3. 刷新界面,侧边栏就会出现这个选举

## 统一 Schema(关键)

每行 = 一条 **微观计数**(不是单个受访者,也不是聚合到顶的总数):

```json
{
  "pollster": "YouGov",
  "survey_date": "2026-11-01",
  "method": "online",
  "age_bin": "18-29",
  "gender": "female",
  "region": "northeast",
  "education": "college",
  "party": "D",
  "n": 214,
  "weighted_n": 218.7
}
```

设计要点:
- **存计数表,不存微观记录**: 各家公布的多是交叉表,微观数据拿不到;计数表足够支持任何 `groupby` 切分。
- **原始计数 `n` 与加权 `weighted_n` 并存**: 保留审计线索。
- **维度可扩展**: 加 `race`、`income`、`religion` 只需加一列。

## 加权方法(raking / IPF)

目标: 让样本在年龄、性别、地区等维度上的边缘分布逼近人口普查基准。

实现见 `src/weight.py`,核心是迭代比例拟合:

```
循环直到收敛:
  for 每个目标维度(age, gender, region...):
    缩放该维度的权重,使其边缘分布 = 基准分布
```

## 使用方法

```bash
pip install -r requirements.txt

# 启动分析界面 (推荐)
streamlit run app.py

# 或命令行加权流水线
python scripts/weight/run_pipeline.py --pollster yougov --election my_election

# 或命令行切支持率
python scripts/analyze/crosstab.py --pollster pollco --party PartyA
```

## 技术选型

| 需求 | 选择 | 理由 |
|---|---|---|
| 数据清洗 | pandas / polars | 交叉表操作直观 |
| 加权 | 自实现 IPF | 无重依赖,可审计 |
| 复杂抽样(进阶) | R `survey` 包 | 民调统计黄金标准 |
| 可视化 | plotly / altair | 交互式人口金字塔 |

## 参考

### 类似项目
- FiveThirtyEight `data` 仓库(github.com/fivethirtyeight/data): 美国民调数据标准化范本
- YouGov / The Economist 的 MRP 模型公开方法论
- R `survey`、`anesrake`、`ipfr` 包: 加权现成实现

### 关键论文(加权 + 子群体估计)
- **Gelman & Little (1997)** *Poststratification into many categories using hierarchical logistic regression*, Survey Methodology — 多维度细分估计的起点
- **Park, Gelman & Bafumi (2004)** *Bayesian multilevel estimation with poststratification*, Political Analysis — MRP 方法奠基,正是"从全国民调推州/人群支持率"
- **Wang, Rothschild, Goel & Gelman (2015)** *Forecasting elections with non-representative polls*, IJF — 非概率样本(Xbox 民调)如何加权修正
- **Lumley (2004)** *Analysis of complex survey samples*, JSS — `survey` 包理论基础

> 若你分析的是"支持者画像"(哪类人支持谁),MRP 与 raking 是最对口的两个方法,建议先读 Gelman & Little 1997 那篇。
