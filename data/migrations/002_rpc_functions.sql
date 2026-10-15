-- ============================================================
-- Supabase RPC 함수 - 집계 및 에이징
-- SQL Editor 에서 실행
-- ============================================================

-- 1. 주간 섹터 집계 (매주 월요일 실행)
CREATE OR REPLACE FUNCTION upsert_weekly_sector_stats()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO weekly_sector_stats (week_start, sector_id, mention_count, rank)
  WITH agg AS (
    SELECT
      date_trunc('week', rm.mentioned_at)::date AS week_start,
      s.sector_id,
      COUNT(DISTINCT rm.id)                      AS mention_count
    FROM raw_mentions rm
    JOIN stocks s USING (ticker)
    GROUP BY 1, 2
  )
  SELECT
    week_start,
    sector_id,
    mention_count,
    RANK() OVER (PARTITION BY week_start ORDER BY mention_count DESC) AS rank
  FROM agg
  ON CONFLICT (week_start, sector_id) DO UPDATE
    SET mention_count = EXCLUDED.mention_count,
        rank          = EXCLUDED.rank;
END;
$$;

-- 2. 월간 종목 집계 (매월 1일 실행)
CREATE OR REPLACE FUNCTION upsert_monthly_stock_stats()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  cur_month  DATE := date_trunc('month', NOW())::date;
  prev_month DATE := (cur_month - INTERVAL '1 month')::date;
BEGIN
  INSERT INTO monthly_stock_stats (month, ticker, mention_count, delta_vs_prev_month, trend)
  SELECT
    cur_month,
    ticker,
    cur.mention_count,
    cur.mention_count - COALESCE(prev.mention_count, 0) AS delta_vs_prev_month,
    CASE
      WHEN cur.mention_count > COALESCE(prev.mention_count, 0) THEN 'up'
      WHEN cur.mention_count < COALESCE(prev.mention_count, 0) THEN 'down'
      ELSE 'flat'
    END AS trend
  FROM (
    SELECT ticker, COUNT(DISTINCT id) AS mention_count
    FROM raw_mentions
    WHERE mentioned_at >= cur_month
      AND mentioned_at <  cur_month + INTERVAL '1 month'
    GROUP BY ticker
  ) cur
  LEFT JOIN (
    SELECT ticker, mention_count
    FROM monthly_stock_stats
    WHERE month = prev_month
  ) prev USING (ticker)
  ON CONFLICT (month, ticker) DO UPDATE
    SET mention_count       = EXCLUDED.mention_count,
        delta_vs_prev_month = EXCLUDED.delta_vs_prev_month,
        trend               = EXCLUDED.trend;
END;
$$;

-- 3. 에이징 (AGING_WEEKS 초과 raw_mentions -> archived_mentions 이동)
CREATE OR REPLACE FUNCTION archive_old_mentions(weeks INT DEFAULT 13)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  cutoff DATE := (NOW() - (weeks || ' weeks')::INTERVAL)::date;
BEGIN
  -- 아카이브로 복사
  INSERT INTO archived_mentions (id, mentioned_at, ticker, source, doc_id, created_at)
  SELECT id, mentioned_at, ticker, source, doc_id, created_at
  FROM raw_mentions
  WHERE mentioned_at < cutoff
  ON CONFLICT (id) DO NOTHING;

  -- 원본 삭제
  DELETE FROM raw_mentions
  WHERE mentioned_at < cutoff;
END;
$$;
