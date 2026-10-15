"""
네이버 종목토론방(종토방) 수집기.

ticker별 URL로 직접 접근하므로 종목 매칭 불필요.
source = 'community'로 raw_mentions에 upsert.
"""

import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from collector.sources.sentiment import analyze_sentiment

BOARD_URL = "https://finance.naver.com/item/board.naver"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DELAY = 0.5  # 요청 간 딜레이 (초)


def _parse_date(date_str: str) -> str:
    """
    네이버 종토방 날짜 파싱.
    "YYYY.MM.DD HH:MM" → "YYYY-MM-DD"
    "HH:MM" (오늘 게시글) → 오늘 날짜
    """
    date_str = date_str.strip()
    if "." in date_str:
        # "2026.06.16 14:01" → "2026-06-16"
        return date_str[:10].replace(".", "-")
    # "14:01" 형식이면 오늘 날짜
    return date.today().isoformat()


def collect_board(tickers: list[str], pages: int = 1) -> list[dict]:
    """
    네이버 종목토론방 수집.

    Args:
        tickers: 수집할 종목코드 목록
        pages: 종목당 수집 페이지 수 (1페이지 = 게시글 15건)

    Returns:
        raw_mentions 형식의 레코드 리스트
    """
    records = []

    for ticker in tickers:
        for page in range(1, pages + 1):
            try:
                resp = requests.get(
                    BOARD_URL,
                    params={"code": ticker, "page": page},
                    headers=HEADERS,
                    timeout=10,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"[board] {ticker} p{page} 요청 실패: {e}")
                time.sleep(DELAY)
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table.type2 tr")

            for row in rows:
                title_td = row.select_one("td.title a")
                tds = row.find_all("td")
                # 날짜는 첫 번째 td (class 없음), 제목은 td.title
                if not title_td or not tds:
                    continue

                title = title_td.get_text(strip=True)
                date_str = tds[0].get_text(strip=True)

                href = title_td.get("href", "")
                # href 예: /item/board_read.naver?code=005930&nid=12345
                if "nid=" in href:
                    post_id = href.split("nid=")[-1].split("&")[0]
                else:
                    # fallback: 제목 해시
                    post_id = str(abs(hash(title)))[:10]

                doc_id = f"naver_board:{ticker}:{post_id}"
                mentioned_at = _parse_date(date_str)
                sentiment = analyze_sentiment(title)

                records.append({
                    "mentioned_at": mentioned_at,
                    "ticker": ticker,
                    "source": "community",
                    "doc_id": doc_id,
                    "sentiment": sentiment,
                })

            time.sleep(DELAY)

    return records
