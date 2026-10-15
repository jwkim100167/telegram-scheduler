"""
네이버 증권 리서치 수집기.

네이버 증권 기업분석 리포트 목록 페이지에서
여러 증권사(미래에셋, 키움, 한투, 하나, KB 등)의 리포트를 한 번에 수집한다.
PDF 다운로드 없이 제목만으로 종목명 매칭.
"""

import logging
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from collector.db.supabase_client import upsert_mentions
from collector.matcher.keyword_matcher import KeywordMatcher
from collector.sources.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)

BASE_URL = "https://finance.naver.com/research/company_list.naver"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/research/",
}
MAX_PAGES = 3         # 일반 수집: 최근 3페이지
BACKFILL_PAGES = 2000  # 백필: 최대 2000페이지 (약 2018년 초까지 커버)


def _parse_date(date_str: str | None) -> date:
    if date_str:
        for fmt in ("%y.%m.%d", "%Y.%m.%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
    return datetime.now().date()


def _fetch_page(page: int) -> list[dict]:
    resp = requests.get(BASE_URL, params={"page": page}, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table.type_1 tr"):
        tds = row.select("td")
        if len(tds) < 5:
            continue

        corp_name = tds[0].get_text(strip=True)
        title     = tds[1].get_text(strip=True)
        broker    = tds[2].get_text(strip=True)
        date_str  = tds[4].get_text(strip=True)  # 인덱스 4: 날짜 (3은 목표가)

        if not corp_name or not title:
            continue

        link_tag = tds[1].select_one("a")
        href = link_tag["href"] if link_tag and link_tag.get("href") else f"{corp_name}:{title}"
        doc_id = f"naver_research:{href}"

        items.append({
            "corp_name": corp_name,
            "title":     title,
            "broker":    broker,
            "date_str":  date_str,
            "doc_id":    doc_id,
        })

    return items


def _items_to_records(items: list[dict], matcher: KeywordMatcher, cutoff: date | None = None) -> list[dict]:
    records = []
    for item in items:
        mentioned_at = _parse_date(item["date_str"])
        if cutoff and mentioned_at < cutoff:
            continue
        text = item["corp_name"] + " " + item["title"]
        sentiment = analyze_sentiment(text)
        for ticker in matcher.match(text):
            records.append({
                "mentioned_at": mentioned_at.isoformat(),
                "ticker":       ticker,
                "source":       "report",
                "doc_id":       item["doc_id"],
                "sentiment":    sentiment,
            })
    return records


def collect_naver_research(matcher: KeywordMatcher) -> int:
    logger.info("네이버 증권 리서치 수집 시작 (최대 %d페이지)", MAX_PAGES)
    records: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        try:
            items = _fetch_page(page)
            logger.info("페이지 %d: %d건 수신", page, len(items))
        except Exception as e:
            logger.error("페이지 %d 수집 실패: %s", page, e)
            break
        records.extend(_items_to_records(items, matcher))

    count = upsert_mentions(records)
    logger.info("네이버 리서치 수집 완료: %d건 처리", count)
    return count


def collect_naver_research_backfill(matcher: KeywordMatcher, days: int = 14) -> int:
    """과거 days일치 리서치 백필. cutoff 이전 데이터가 나오면 자동 중단."""
    cutoff = datetime.now().date() - timedelta(days=days)
    logger.info("네이버 리서치 백필 시작 (기준: %d일 전, %s 이후)", days, cutoff)

    records: list[dict] = []
    for page in range(1, BACKFILL_PAGES + 1):
        try:
            items = _fetch_page(page)
        except Exception as e:
            logger.error("페이지 %d 수집 실패: %s", page, e)
            break

        if not items:
            break

        page_records = _items_to_records(items, matcher, cutoff=cutoff)
        records.extend(page_records)

        # 페이지 내 최신 날짜가 cutoff 이전이면 더 이상 볼 필요 없음
        dates = [_parse_date(i["date_str"]) for i in items]
        oldest = min(dates)
        logger.info("페이지 %d: 최오래된 날짜 %s, 누적 %d건", page, oldest, len(records))
        if oldest < cutoff:
            break

    count = upsert_mentions(records)
    logger.info("네이버 리서치 백필 완료: %d건 처리", count)
    return count
