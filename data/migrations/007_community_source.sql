-- ============================================================
-- 007: 종목토론방(community) 소스 추가
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1) raw_mentions source 제약에 'community' 추가
ALTER TABLE raw_mentions
  DROP CONSTRAINT IF EXISTS raw_mentions_source_check;

ALTER TABLE raw_mentions
  ADD CONSTRAINT raw_mentions_source_check
  CHECK (source IN ('dart', 'naver', 'report', 'community'));

-- 2) weekly_sector_stats에 소스별 컬럼 추가
ALTER TABLE weekly_sector_stats
  ADD COLUMN IF NOT EXISTS report_count    INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS community_count INT NOT NULL DEFAULT 0;

-- 3) upsert_weekly_sector_stats 함수 업데이트
--    (소스별 카운트 분리, DART 제외 유지)
CREATE OR REPLACE FUNCTION upsert_weekly_sector_stats() RETURNS void AS $$
BEGIN
  INSERT INTO weekly_sector_stats
    (week_start, sector_id, mention_count, positive_count, rank, report_count, community_count)
  WITH base AS (
    SELECT
      date_trunc('week', rm.mentioned_at::date)::date AS week_start,
      s.sector_id,
      rm.sentiment,
      rm.source
    FROM raw_mentions rm
    JOIN stocks s ON s.ticker = rm.ticker
    WHERE s.sector_id IS NOT NULL
      AND rm.source != 'dart'
  )
  SELECT
    week_start,
    sector_id,
    COUNT(*)                                          AS mention_count,
    COUNT(*) FILTER (WHERE sentiment = 1)             AS positive_count,
    RANK() OVER (PARTITION BY week_start ORDER BY COUNT(*) DESC) AS rank,
    COUNT(*) FILTER (WHERE source = 'report')         AS report_count,
    COUNT(*) FILTER (WHERE source = 'community')      AS community_count
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
