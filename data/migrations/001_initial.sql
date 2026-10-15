-- ============================================================
-- 불타기 투자 대시보드 초기 스키마
-- Supabase SQL Editor 에서 한 번 실행
-- ============================================================

-- 1. 섹터
CREATE TABLE IF NOT EXISTS sectors (
  sector_id   TEXT PRIMARY KEY,
  sector_name TEXT NOT NULL
);

-- 2. 종목
CREATE TABLE IF NOT EXISTS stocks (
  ticker    TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  sector_id TEXT REFERENCES sectors(sector_id),
  aliases   TEXT[]           -- 별칭/약칭 배열 (예: {"삼전","삼성전자우"})
);

-- 3. 원시 언급 테이블 (핵심)
CREATE TABLE IF NOT EXISTS raw_mentions (
  id           BIGSERIAL PRIMARY KEY,
  mentioned_at DATE        NOT NULL,
  ticker       TEXT        REFERENCES stocks(ticker),
  source       TEXT        NOT NULL CHECK (source IN ('dart', 'naver', 'report')),
  doc_id       TEXT        NOT NULL,    -- 원문 식별자 (URL or 고유ID)
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (doc_id, ticker)              -- 같은 문서에서 같은 종목 중복 적재 방지
);

CREATE INDEX IF NOT EXISTS idx_raw_mentions_mentioned_at ON raw_mentions(mentioned_at);
CREATE INDEX IF NOT EXISTS idx_raw_mentions_ticker       ON raw_mentions(ticker);

-- 4. 아카이브 (13주 초과 데이터 이동)
CREATE TABLE IF NOT EXISTS archived_mentions (
  id           BIGINT      PRIMARY KEY,
  mentioned_at DATE        NOT NULL,
  ticker       TEXT,
  source       TEXT,
  doc_id       TEXT,
  created_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_archived_mentions_mentioned_at ON archived_mentions(mentioned_at);

-- 5. 주간 섹터 집계
CREATE TABLE IF NOT EXISTS weekly_sector_stats (
  week_start    DATE NOT NULL,
  sector_id     TEXT REFERENCES sectors(sector_id),
  mention_count INT  NOT NULL DEFAULT 0,
  rank          INT,
  PRIMARY KEY (week_start, sector_id)
);

-- 6. 월간 종목 집계
CREATE TABLE IF NOT EXISTS monthly_stock_stats (
  month               DATE NOT NULL,   -- 해당 월의 1일
  ticker              TEXT REFERENCES stocks(ticker),
  mention_count       INT  NOT NULL DEFAULT 0,
  delta_vs_prev_month INT,             -- 전월 대비 증감 (null = 첫 달)
  trend               TEXT CHECK (trend IN ('up', 'down', 'flat')),
  PRIMARY KEY (month, ticker)
);
