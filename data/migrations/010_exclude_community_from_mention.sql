-- ============================================================
-- 010: mention_count에서 community 제외
--      (community_count 컬럼은 유지, mention_count = naver+report만)
--      + mentioned_at 주차 경계 KST 기준으로 수정
-- Supabase SQL Editor에서 실행 후 aggregate 재실행
-- ============================================================

CREATE OR REPLACE FUNCTION upsert_weekly_sector_stats() RETURNS void AS $$
BEGIN
  INSERT INTO weekly_sector_stats
    (week_start, sector_id, mention_count, positive_count, rank, report_count, community_count)
  WITH base AS (
    SELECT
      date_trunc('week', rm.mentioned_at AT TIME ZONE 'Asia/Seoul')::date AS week_start,
      s.sector_id,
      rm.sentiment,
      rm.source
    FROM raw_mentions rm
    JOIN stocks s ON s.ticker = rm.ticker
    WHERE s.sector_id IS NOT NULL
      AND rm.source NOT IN ('dart', 'community')   -- DART·커뮤니티 제외
  )
  SELECT
    week_start,
    sector_id,
    COUNT(*)                                          AS mention_count,
    COUNT(*) FILTER (WHERE sentiment = 1)             AS positive_count,
    RANK() OVER (PARTITION BY week_start ORDER BY COUNT(*) DESC) AS rank,
    COUNT(*) FILTER (WHERE source = 'report')         AS report_count,
    0                                                 AS community_count
  FROM base
  GROUP BY week_start, sector_id
  ON CONFLICT (week_start, sector_id) DO UPDATE SET
    mention_count   = EXCLUDED.mention_count,
    positive_count  = EXCLUDED.positive_count,
    rank            = EXCLUDED.rank,
    report_count    = EXCLUDED.report_count,
    community_count = EXCLUDED.community_count;
END;
$$ LANGUAGE plpgsql;
