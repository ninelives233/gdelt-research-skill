---
name: gdelt-research
description: 检索、筛选和下载 GDELT 的新闻元数据、报道趋势、Events 与 GKG 数据，解释字段并保留可复现记录。适用于地缘政治、贸易战、冲突、疫情等新闻与事件数据研究；不用于取得金融行情或把新闻情绪直接解释为金融安全。
---

# GDELT 研究

先确定主题、日期、数据单位和交付范围。资料足够时直接执行；未给日期的教学任务先用明确标注的短期样例，不把演示日期当成正式研究区间。

## 请用户决定前，先解释

- 需要用户选择时，先用日常语言解释可能陌生的名词：它是什么、能得到什么、适合回答什么问题。技术名称可放在括号中；不要直接让初学者在 DOC、Events、GKG、BigQuery 等缩写间选择。
- 每个选项说明具体产物和影响。例如“报道清单”能逐条查看新闻链接，“事件记录”帮助看谁对谁做了什么；说明是否含全文、是否要人工核验等与本次决定有关的限制。不能只把英文名换成同样难懂的中文名。
- 询问规模时，把“样例／批次／按日期采集”换成明确的时间、覆盖范围和用途。解释一个 15 分钟更新包不是当天全部数据；预计下载量、耗时或费用未知时直说，先小范围探测，不编造估计，也不把输出行数当作下载规模。
- 根据用户目的给出推荐及简短理由，保留选择其他方案的空间。只问真正影响结果的事项；用户已经决定的条件直接沿用，可自行处理的技术参数自行处理，不增加重复确认。
- 使用选择工具时，把理解当前决定所需的解释写进该条问题或各选项说明，保证选项离开先前对话也看得懂。先解释，再提问；不在用户选完后才补充关键区别。解释深度随用户经验调整，不必每次讲完整套术语。

数据类型、规模和下载方式的通俗解释与提问示例见 [references/decision-guidance.md](references/decision-guidance.md)。这些是按需改写的例子，不是每次都要问的固定问卷。

## 选择路径

| 需要 | 路径 | 数据单位 |
|---|---|---|
| 人工学习、查看新闻 | [GDELT Summary](https://api.gdeltproject.org/api/v2/summary/summary?d=web&t=summary) | 看板和有限新闻列表 |
| 英文关键词检索、导出链接 | DOC 2.0，脚本 doc | 新闻元数据，无全文或逐篇数值 tone |
| 报道数量、关注度、平均情绪 | DOC，脚本 timeline | 时间桶聚合 |
| 谁对谁做什么、CAMEO 与 Goldstein | Events，脚本 events 或 BigQuery | 机器抽取的事件记录 |
| 主题、人物、机构、地点、文章情绪 | GKG，脚本 gkg 或 BigQuery | 文档特征 |
| 多年大规模数据、事件与主题联结 | 分区 BigQuery 表 | 先确认结构、覆盖期和扫描量 |

按需阅读 [references/operations.md](references/operations.md)，包括网页选项、API 时限差异、字段和脚本用法。多年查询可从 [references/bigquery.sql](references/bigquery.sql) 改写；模板不能声称已执行。

## 检索与验证

1. 将概念转为关键词组或官方字典中确实存在的主题。英文关键词可命中非英文报道的机器译文。OR 用大写，组不嵌套；同时出现用空格。中美贸易战先试 `China "trade war"`，再比较 `China ("trade war" OR tariff OR tariffs) ("United States" OR USA OR American)`；仅查 trade 会混入大量无关报道。
2. 现场验证日期范围和接口。旧文档有三个月、一年、自 2017 年起等不同说明。实测 2018 年新闻可返回，但不保证每种模式/日期都可用。非 timeline 模式使用不超过 31 天的窗口，避开长窗口只考虑尾部的机制。
3. 新闻 API 请求串行，至少间隔 6 秒；不并行运行多个实例。实测服务提示每 5 秒最多一次。429 有限退避，持续失败就保留错误并停止；不把 HTML 或错误正文当成空数据。
4. 使用 `scripts/gdelt_fetch.py`（Python 3.10+、curl，无 pip 依赖）。输出到新目录；保留 raw、requests.json、manifest.json、CSV/JSON。脚本时间均为 UTC，end 不包含；中国时间减 8 小时。原始包时间是更新时点，不是事件发生日期。
5. doc 最多 250 条/请求；触顶拆窗，最小子窗口约 15 分钟，受请求预算约束。检查 unresolved_windows、失败状态、边界外记录。sample 明确只取样。未观测到截断也不代表全球全部新闻；URL 去重不去除不同网站的转载。
6. 检查相关性、日期、来源；保留结构化原字段，CAMEO 代码用字符串。双向 CHN/USA 仅表示中美互动；GKG 的 CH/US 地点共现仅表示同文提及两地，均须进一步核验贸易战相关性。区分 Actor CAMEO 国家、Geo FIPS 和媒体来源国。
7. 交付检索式、时间、筛选条件、单位、行数、字段、测试状态及完整性说明。人工标签另存并附依据，不覆盖机器原值。

## 最小调用

以下路径相对技能目录；输出目录必须尚不存在。

```bash
python3 scripts/gdelt_fetch.py doc --query 'China "trade war"' --start 2018-07-06 --end 2018-07-08 --sample --max-records 50 --out ./trade-news
python3 scripts/gdelt_fetch.py timeline --query 'China "trade war"' --start 2018-07-01 --end 2018-07-11 --mode timelinevolraw --out ./trade-volume
python3 scripts/gdelt_fetch.py events --timestamp 20180706120000 --actor1 CHN --actor2 USA --out ./trade-events
python3 scripts/gdelt_fetch.py gkg --timestamp 20180706120000 --theme ECON_TRADE_DISPUTE --countries CH US --out ./trade-gkg
```

金融安全研究应将新闻/事件指标按日或周聚合，再与选定的外部金融变量合并。GDELT 不提供中国股价、汇率、资本流动或因果效应；Goldstein 是事件类型赋分，tone 是文本情绪，均不是金融损失。
