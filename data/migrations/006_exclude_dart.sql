-- DART 공시 제외 버전으로 집계 함수 교체
-- 분기보고서 등 의무 공시는 시장 관심 신호가 아니므로 제외
-- source: 'dart' | 'naver' | 'report'
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
    AND rm.source != 'dart'          -- DART 공시 제외
  GROUP BY week_start, s.sector_id
  ON CONFLICT (week_start, sector_id) DO UPDATE SET
    mention_count  = EXCLUDED.mention_count,
    positive_count = EXCLUDED.positive_count,
    negative_count = EXCLUDED.negative_count,
    rank           = EXCLUDED.rank;
END;
$$;
