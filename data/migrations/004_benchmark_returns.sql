-- 코스피/코스닥 벤치마크 주간 수익률
-- KODEX 200 (069500) = 코스피200 추종
-- KODEX KOSDAQ150 (229200) = 코스닥150 추종
CREATE TABLE IF NOT EXISTS weekly_benchmark_returns (
  week_start    DATE PRIMARY KEY,
  kospi200_ret  FLOAT,   -- KODEX200 주간 수익률 (%)
  kosdaq150_ret FLOAT    -- KODEX KOSDAQ150 주간 수익률 (%)
);

ALTER TABLE weekly_benchmark_returns DISABLE ROW LEVEL SECURITY;
