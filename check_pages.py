import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

for page in [500, 1000, 2000, 3000, 4000]:
    resp = requests.get('https://finance.naver.com/research/company_list.naver',
                        params={'page': page}, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    rows = soup.select('table.type_1 tr')
    dates = [r.select('td')[4].get_text(strip=True) for r in rows if len(r.select('td')) >= 5]
    oldest = min(dates) if dates else 'N/A'
    print(f'page {page}: {len(dates)}건, 가장 오래된 날짜={oldest}')
