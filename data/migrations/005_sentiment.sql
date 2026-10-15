-- raw_mentions 에 감성 점수 추가
ALTER TABLE raw_mentions
  ADD COLUMN IF NOT EXISTS sentiment SMALLINT DEFAULT 0;  -- +1 긍정, -1 부정, 0 중립

-- weekly_sector_stats 에 감성 집계 컬럼 추가
ALTER TABLE weekly_sector_stats
  ADD COLUMN IF NOT EXISTS positive_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS negative_count INT DEFAULT 0;

-- Supabase 집계 함수 교체: 감성 포함 버전
CREATE OR REPLACE FUNCTION upsert_weekly_sector_stats()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO weekly_sector_stats (week_start, sector_id, mention_count, positive_count, negative_count, rank)
  SELECT
    date_trunc('week', rm.mentioned_at::date)::date  AS week_start,
    s.sector_id,
    COUNT(*)                                          AS mention_count,
    COUNT(*) FILTER (WHERE rm.sentiment =  1)         AS positive_count,
    COUNT(*) FILTER (WHERE rm.sentiment = -1)         AS negative_count,
    RANK() OVER (
      PARTITION BY date_trunc('week', rm.mentioned_at::date)
      ORDER BY COUNT(*) DESC
    )                                                 AS rank
  FROM raw_mentions rm
  JOIN stocks s ON s.ticker = rm.ticker
  WHERE s.sector_id IS NOT NULL
  GROUP BY week_start, s.sector_id
  ON CONFLICT (week_start, sector_id) DO UPDATE SET
    mention_count  = EXCLUDED.mention_count,
    positive_count = EXCLUDED.positive_count,
    negative_count = EXCLUDED.negative_count,
    rank           = EXCLUDED.rank;
END;
$$;
