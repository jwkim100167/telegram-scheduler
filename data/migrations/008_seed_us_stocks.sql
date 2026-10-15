-- ============================================================
-- 008: NASDAQ Top10 종목 시드
-- Supabase SQL Editor에서 실행
-- ============================================================

INSERT INTO stocks (ticker, name, sector_id, aliases) VALUES
  ('AAPL',  'Apple',     'NASDAQ_TOP10', ARRAY['애플', 'AAPL', 'Apple']),
  ('MSFT',  'Microsoft', 'NASDAQ_TOP10', ARRAY['마이크로소프트', '마소', 'MSFT', 'Microsoft']),
  ('NVDA',  'NVIDIA',    'NASDAQ_TOP10', ARRAY['엔비디아', 'NVDA', 'NVIDIA']),
  ('AMZN',  'Amazon',    'NASDAQ_TOP10', ARRAY['아마존', 'AMZN', 'Amazon']),
  ('GOOGL', 'Alphabet',  'NASDAQ_TOP10', ARRAY['알파벳', '구글', 'GOOGL', 'GOOG', 'Google']),
  ('META',  'Meta',      'NASDAQ_TOP10', ARRAY['메타', 'META', 'Meta', '페이스북', 'Facebook']),
  ('TSLA',  'Tesla',     'NASDAQ_TOP10', ARRAY['테슬라', 'TSLA', 'Tesla']),
  ('AVGO',  'Broadcom',  'NASDAQ_TOP10', ARRAY['브로드컴', 'AVGO', 'Broadcom']),
  ('COST',  'Costco',    'NASDAQ_TOP10', ARRAY['코스트코', 'COST', 'Costco']),
  ('NFLX',  'Netflix',   'NASDAQ_TOP10', ARRAY['넷플릭스', 'NFLX', 'Netflix'])
ON CONFLICT (ticker) DO UPDATE SET
  sector_id = EXCLUDED.sector_id,
  aliases   = EXCLUDED.aliases;
