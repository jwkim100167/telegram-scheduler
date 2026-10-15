-- 주간 섹터 수익률 테이블
-- Supabase SQL Editor에서 실행

CREATE TABLE IF NOT EXISTS weekly_sector_returns (
  week_start   DATE NOT NULL,
  sector_id    TEXT REFERENCES sectors(sector_id),
  return_pct   FLOAT NOT NULL,   -- 해당 주 섹터 등가중 수익률 (%)
  stock_count  INT  NOT NULL,    -- 계산에 포함된 종목 수
  PRIMARY KEY (week_start, sector_id)
);
