# 操作与数据口径

核实日期：2026-10-20。依据为实际 Summary HTML、API 响应和官方文档。服务状态、限额和字段在正式采集时复查。

## 人工入口

打开 https://api.gdeltproject.org/api/v2/summary/summary?d=web&t=summary 。

- Step 1 / Dataset：Global Online News Coverage。
- Step 2 / Output Type：Summary Overview Dashboard。
- Step 3 / Keyword(s)：英文检索式，如 `China "trade war"`。Time Period 选 Past Week 或 Custom Date Range；日期框为 mm/dd/yyyy。
- Limit To Country 是媒体所在地；Limit To Language 是原文语言，均不是事件当事国。
- Smoothing：No Smoothing (Exact Dates/Times)。
- Step 4 / Volume Timeline：Include Basic (% Monitored Articles) 或 Include Basic (Raw Article Count)；Tone Timeline：Include；Top Matching Articles：Text List (All Matching Articles)。All 表示不要求图片，不表示取消条数上限。
- 点 Create Summary；各图表的 Export 菜单下载 CSV/JSON，文字以现场界面为准。总看板慢可打开单个 DOC 图表并缩短时间范围。
- 地图有独立近期窗口，不应当成自选历史时段地图；页面不同说明存在 24h/7d 差异，查看生成图表的时间标签。

## 参数与字段

DOC 基址：https://api.gdeltproject.org/api/v2/doc/doc 。query 中放检索操作符；mode、format、startdatetime、enddatetime、maxrecords、sort 是 URL 参数。使用 urlencode 编码。format=json/csv 可导出，HTML 是浏览器图表。

artlist 常见字段：url、url_mobile、title、seendate、socialimage、domain、language、sourcecountry。seendate 作为 GDELT 观察时间；实测历史数据可能出现整天时间桶和请求边界外返回值。脚本按原始 seendate 在全局范围内再筛选，不把它伪装成精确发布时间。列表不包含全文或逐篇数值 tone。timelinevolraw 是匹配文档数；norm（若返回）是全部监测文档基数；timelinevol 是关注度百分比；timelinetone 是匹配文章平均语调。

Events ZIP 每 15 分钟一份，无表头，名叫 CSV 实为 tab 分隔，61 列。脚本提供列名，保留 EventCode 前导零。核心字段：GLOBALEVENTID、SQLDATE、DATEADDED、Actor1/2CountryCode、EventCode、QuadClass、GoldsteinScale、NumMentions、NumSources、NumArticles、AvgTone、ActionGeo_*、SOURCEURL。SQLDATE 是抽取的事件日期，DATEADDED 是入库时点。NumMentions/NumSources/NumArticles 是首次发现更新时段的量，不是全生命周期累计量；传播轨迹需另查 eventmentions，按事件 ID 与文档 URL/时间口径去重。

GKG 原始数据 27 列。Themes 为分号隔开的主题；V2Themes 还带偏移。V2Locations 的条目用分号分隔，各条内部用 # 分隔，第三部分为 FIPS 国家代码。V2Tone 第一个逗号分量为文章整体 tone，其余见 codebook。主题命中与国家共现只是候选筛选条件。

Actor 中国/美国：CHN/USA；Geo FIPS：中国 CH、美国 US。sourcecountry:china 选择中国媒体，不代替研究对象中国。

## 下载器

gdelt_fetch.py 有 doc、timeline、events、gkg 四个子命令。输出目录必须新建。联网依赖 curl，其他为 Python 标准库。

- start/end 接受 YYYY-MM-DD 或 YYYYMMDDHHMMSS（UTC），结束不包含。
- max-requests 默认 64，含失败重试。interval 最小 6 秒；DOC 客户端串行。
- doc --sample --max-records 50：短期教学取样。默认 doc 最多 250 条/请求，触顶拆窗；时间窗最长 31 天。最小窗口仍触顶明确标为未解决。
- timeline --mode timelinevolraw|timelinevol|timelinetone：保留 API 时间桶、norm，不擅自填补缺失。
- events --timestamp 20180706120000 --actor1 CHN --actor2 USA：下载一个更新包，双向筛选；不是整天数据。
- gkg --timestamp 20180706120000 --theme ECON_TRADE_DISPUTE --countries CH US：精确主题和两国地点共现。
- events/gkg 可用 --zip /absolute/path/data.zip 离线重放；先核对内容与 timestamp 一致。脚本保留 hash，不证明输入文件名与内容时间一致。

raw 为证据，CSV 为副本，manifest 为范围/状态说明，requests.json 为追踪。非零退出码表示失败，保留已下载内容。原字符串在 JSON/ZIP；Excel 导入 CSV 时把 EventCode、ID 等设为文本。

检查 status、exported_rows、completeness、unresolved_windows、pending_windows、outside_requested_window、HTTP 状态与 hash。错误或仅表头不表示主题不存在。短窗口 250 条表示触顶，不是总共仅 250 条。

## 大规模下载

索引：https://data.gdeltproject.org/gdeltv2/lastupdate.txt ，含文件大小、MD5、HTTP URL，可改为 HTTPS。历史按 UTC 的 YYYYMMDDHHMMSS 命名。一天通常 96 个更新包；正式采集记录缺包、重试和校验状态。本脚本 archive 模式只处理一个更新包；多年批量选 BigQuery 或另做带断点和清单的采集。

BigQuery 见同目录 bigquery.sql。确认分区表名、schema、时间覆盖后用 dry run/界面估算扫描量。LIMIT 限制返回行数，通常不降低扫描字节；须约束分区字段。GDELT 数据免费不等于任意 Google Cloud 计算免费。没有登录和执行就报告模板未执行。

## 官方依据

- https://gdeltproject.org/data.html
- https://blog.gdeltproject.org/announcing-gdelt-summary/
- https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/
- https://blog.gdeltproject.org/updates-doc-2-0-api/
- https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
- https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf
- https://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT
- https://blog.gdeltproject.org/complex-queries-combining-events-eventmentions-and-gkg/
- https://blog.gdeltproject.org/announcing-partitioned-gdelt-bigquery-tables/
- https://docs.cloud.google.com/bigquery/docs/sandbox
