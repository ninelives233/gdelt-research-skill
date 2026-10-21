# GDELT Research Skill

面向中文研究团队的 Codex skill：检索和下载 GDELT 新闻、事件与主题数据，保留原始文件、筛选条件和下载记录。可直接下载官方原始数据包，不需要 BigQuery 账号。

## 安装到 Codex

把下面这句话发给 Codex：

```text
使用 $skill-installer 安装这个 GitHub 仓库中的 gdelt-research skill：
https://github.com/ninelives233/gdelt-research-skill/tree/main/gdelt-research
```

安装后在下一轮对话中使用：

```text
使用 $gdelt-research，不用 BigQuery，下载 2018 年 7 月 6 日
12:00 UTC 更新批次的 GKG 数据，筛选贸易争端主题和中国、美国地点共现，
导出 CSV，并说明筛选口径、字段及完整性。
```

## 需要你选择时怎么说明

Skill 会先用通俗语言说明相关名词、每个选项会得到什么，以及对时间、范围、完整性或费用的影响，再请你决定。例如，先解释“报道特征表”和“事件记录”分别能回答什么问题，而不是直接让你在 GKG、Events 等缩写之间选择。根据任务给出推荐，已确定的条件不重复询问。

具体例子见[决策前的解释与提问](gdelt-research/references/decision-guidance.md)。

## 直接运行脚本

不使用 Codex 也能运行下载器。需要 **Python 3.10+ 和 curl**，无额外 pip 依赖。以下命令在仓库根目录执行：

```bash
git clone https://github.com/ninelives233/gdelt-research-skill.git
cd gdelt-research-skill
python3 gdelt-research/scripts/gdelt_fetch.py --help
```

下载一个 GKG 更新包，筛选贸易争端主题与中美地点共现：

```bash
python3 gdelt-research/scripts/gdelt_fetch.py gkg \
  --timestamp 20180706120000 \
  --theme ECON_TRADE_DISPUTE \
  --countries CH US \
  --out ./data/trade-gkg
```

下载一个 Events 更新包，双向筛选中美参与方：

```bash
python3 gdelt-research/scripts/gdelt_fetch.py events \
  --timestamp 20180706120000 \
  --actor1 CHN --actor2 USA \
  --out ./data/china-us-events
```

使用 DOC API 取新闻元数据样例：

```bash
python3 gdelt-research/scripts/gdelt_fetch.py doc \
  --query 'China "trade war"' \
  --start 2018-07-06 --end 2018-07-08 \
  --sample --max-records 50 --max-requests 3 \
  --out ./data/trade-news
```

下载报道数量趋势：

```bash
python3 gdelt-research/scripts/gdelt_fetch.py timeline \
  --query 'China "trade war"' \
  --start 2018-07-01 --end 2018-07-11 \
  --mode timelinevolraw \
  --out ./data/trade-volume
```

所有时间按 **UTC**；`--end` 不包含。`--out` 必须是尚不存在的目录。Events/GKG 的时间戳须对齐 15 分钟。已有原始 ZIP 可用 `--zip /path/to/archive.zip` 离线处理。

## 支持范围与限制

| 路径 | 提供的数据 | 范围与注意事项 |
|---|---|---|
| `gkg` | 来源、原文链接、主题、地点、人物、机构、文章整体情绪 | 每次一个 15 分钟更新包；按主题和地点筛选 |
| `events` | 参与方、事件类型、Goldstein、AvgTone、来源链接等 | 每次一个 15 分钟更新包；按国家参与方双向筛选 |
| `doc` | 新闻标题、链接、观察时间、语言等元数据 | API 有返回上限；非取样模式触顶拆窗，并报告未解决窗口 |
| `timeline` | 报道数量、关注度百分比或平均情绪的时间序列 | 聚合数据，保留接口原始时间桶 |

- **不依赖 BigQuery**：上述四个子命令直接请求 GDELT。仓库另附 BigQuery SQL 作为可选研究模板，未在本项目中执行。
- DOC API 和 Summary 看板可能返回 **429 限流**。缩短时间范围不保证恢复；脚本串行请求、有限重试，失败后保留原始错误并退出，不把失败写成“零结果”。不要并行运行多个下载实例。网页检索持续限流时，可尝试原始数据包路径，但它也依赖网络和服务可用性。
- **原始包目前没有整月／整年批量调度器**；多批次下载需要额外编排，不能把一个批次说成整天或全部报道。
- GKG 的主题命中和中美地点共现、Events 的中美参与方，只形成候选记录；应检查原文相关性。不同网站转载也可能重复。
- 数据不包含新闻全文。`seendate` 是 GDELT 观察时间，更新包时间是入库更新时点；均不等于精确的原文发布时间。
- 国家编码有不同体系：参与方中国／美国用 `CHN/USA`，地理 FIPS 用 `CH/US`；媒体来源国不等于事件当事国。
- Goldstein 是事件类型赋分，tone 是文本情绪，均不是金融损失或对中国金融安全的直接测量。

## 输出与可复现记录

成功运行会在输出目录中生成 CSV、JSON、`manifest.json` 和 `raw/`；联网请求另存 `requests.json`。记录包括检索条件、时间范围、HTTP 状态、原始响应、SHA-256、行数和完整性状态。失败运行以非零状态退出，部分产物会保留。

请先检查 `manifest.json` 的 `status`、`completeness`、`exported_rows` 等字段，再使用结果。CSV 适合查看；原始 ZIP／JSON 保留原值。Excel 导入时将事件代码、ID 等列设置为文本，避免丢失前导零。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

包含 9 个离线行为测试，检查拆窗、去重、时间边界、截断标记、失败保留数据、CSV 字段和限流请求预算。测试使用模拟响应，不需要联网，也不证明实时 API 可用。

在仓库准备前，曾用真实历史原始包验证：`20180706120000` 批次中，Events 共 1,853 行，按中美参与方筛出 7 行；GKG 共 2,558 行，按贸易争端主题及中美地点共现筛出 74 行。这里只说明对应批次与筛选规则的结果，不承诺其他日期有相同数量。

## 文件与资料

- [Skill 入口](gdelt-research/SKILL.md)
- [下载脚本](gdelt-research/scripts/gdelt_fetch.py)
- [人工操作、字段与数据口径](gdelt-research/references/operations.md)
- [可选 BigQuery SQL](gdelt-research/references/bigquery.sql)
- [GDELT 官方数据说明](https://gdeltproject.org/data.html)
- [DOC API 官方说明](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [Codex 技能说明](https://developers.openai.com/codex/skills)

本项目是非官方研究工具，与 GDELT、Google 或 OpenAI 无隶属关系。
