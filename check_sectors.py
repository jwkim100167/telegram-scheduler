import sys
sys.stdout.reconfigure(encoding='utf-8')

from collector.db.supabase_client import get_client

client = get_client()
res = client.table('stocks').select('ticker,name,sector_id').execute()
stocks = res.data

# 섹터별 정렬
from collections import defaultdict
by_sector = defaultdict(list)
for s in stocks:
    by_sector[s['sector_id']].append(f"{s['ticker']} {s['name']}")

for sector in sorted(by_sector.keys()):
    items = by_sector[sector]
    print(f"\n=== {sector} ({len(items)}개) ===")
    for item in sorted(items):
        print(f"  {item}")
