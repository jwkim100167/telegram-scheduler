import requests
from bs4 import BeautifulSoup

resp = requests.get(
    'https://finance.naver.com/item/board.naver',
    params={'code': '005930', 'page': 1},
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
    timeout=10
)
soup = BeautifulSoup(resp.text, 'html.parser')

t2 = soup.select_one('table.type2')
if not t2:
    print('table.type2 없음')
else:
    rows = t2.select('tr')
    print(f'table.type2 tr 수: {len(rows)}')
    for i, row in enumerate(rows[:5]):
        tds = row.find_all('td')
        print(f'\n--- row[{i}] td 수: {len(tds)} ---')
        for j, td in enumerate(tds):
            print(f'  td[{j}] class={td.get("class", [])} text="{td.get_text(strip=True)[:40]}"')
