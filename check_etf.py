import sys
sys.stdout.reconfigure(encoding='utf-8')
import FinanceDataReader as fdr

# 섹터별 대표 ETF 후보 확인
candidates = {
    'SHIPBUILDING':  ('466920', 'SOL 조선TOP3플러스'),
    'DEFENSE':       ('449450', 'PLUS K방산'),
}

for sector, (ticker, name) in candidates.items():
    try:
        df = fdr.DataReader(ticker, '2000-01-01')
        first = df.index[0].strftime('%Y-%m-%d') if not df.empty else 'N/A'
        print(f"{sector:15} {ticker} {name:30} 상장일: {first}")
    except Exception as e:
        print(f"{sector:15} {ticker} {name:30} 오류: {e}")
