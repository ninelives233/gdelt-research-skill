-- GoogleSQL / Standard SQL. Prepared templates; NOT executed in this task.
-- Confirm schema, partition coverage and estimated bytes in BigQuery first.
-- Use the US processing location for the public GDELT dataset.
-- LIMIT limits returned rows, not normally the bytes scanned.
-- Ingestion date is constrained below; SQLDATE may be earlier.

-- 1. Bilateral event candidates first ingested on 2018-07-06 UTC.
-- These are CHN/USA interactions, not a prevalidated trade-war dataset.
SELECT
  GLOBALEVENTID, SQLDATE, DATEADDED,
  Actor1Name, Actor1CountryCode, Actor2Name, Actor2CountryCode,
  EventCode, EventBaseCode, EventRootCode, QuadClass,
  GoldsteinScale, NumMentions, NumSources, NumArticles, AvgTone,
  ActionGeo_FullName, ActionGeo_CountryCode, SOURCEURL
FROM `gdelt-bq.gdeltv2.events_partitioned`
WHERE _PARTITIONTIME >= TIMESTAMP('2018-07-06')
  AND _PARTITIONTIME < TIMESTAMP('2018-07-07')
  AND DATEADDED >= 20180706000000 AND DATEADDED < 20180707000000
  AND ((Actor1CountryCode = 'CHN' AND Actor2CountryCode = 'USA')
    OR (Actor1CountryCode = 'USA' AND Actor2CountryCode = 'CHN'))
ORDER BY DATEADDED, GLOBALEVENTID
LIMIT 1000;

-- 2. Document candidates: exact trade-dispute theme and CH/US location co-occurrence.
-- Themes, not V2Themes, is used for exact tokens without character offsets.
-- Co-occurrence is only a retrieval rule; review the article for actual relevance.
SELECT
  GKGRECORDID, DATE, SourceCommonName, DocumentIdentifier,
  Themes, V2Locations, V2Persons, V2Organizations, V2Tone,
  SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(0)] AS FLOAT64) AS article_tone
FROM `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE _PARTITIONTIME >= TIMESTAMP('2018-07-06')
  AND _PARTITIONTIME < TIMESTAMP('2018-07-07')
  AND DATE >= 20180706000000 AND DATE < 20180707000000
  AND REGEXP_CONTAINS(Themes, r'(^|;)ECON_TRADE_DISPUTE(;|$)')
  AND EXISTS (
    SELECT 1 FROM UNNEST(SPLIT(V2Locations, ';')) AS loc
    WHERE SPLIT(loc, '#')[SAFE_OFFSET(2)] = 'CH'
  )
  AND EXISTS (
    SELECT 1 FROM UNNEST(SPLIT(V2Locations, ';')) AS loc
    WHERE SPLIT(loc, '#')[SAFE_OFFSET(2)] = 'US'
  )
ORDER BY DATE, GKGRECORDID
LIMIT 1000;

-- To connect these document candidates to event records:
-- GKG.DocumentIdentifier = eventmentions.MentionIdentifier
-- eventmentions.GLOBALEVENTID = events.GLOBALEVENTID.
-- Apply separate partition constraints to all scanned tables. Mentions on one day
-- can refer to an event first ingested earlier: choosing the same partition range
-- for all tables restricts the population and can drop earlier events.
-- Aggregate event IDs and document URLs before joining financial series;
-- raw joins multiply rows and can inflate counts.
