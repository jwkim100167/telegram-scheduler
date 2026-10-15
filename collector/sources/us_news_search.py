"""
미국 NASDAQ Top10 종목 뉴스 수집기.

Google News RSS로 각 종목의 한국명을 검색해 언급량을 수집한다.
매처 없이 ticker를 직접 지정하므로 정확도가 높다.
source = 'naver' 로 raw_mentions에 upsert.
"""

import logging
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests

from collector.db.supabase_client import upsert_mentions
from collector.sources.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)

# ticker → (한국명 검색어, 영문명) 매핑
US_STOCK_QUERIES: dict[str, tuple[str, str]] = {
    "AAPL":  ("애플",          "Apple"),
    "MSFT":  ("마이크로소프트", "Microsoft"),
    "NVDA":  ("엔비디아",       "NVIDIA"),
    "AMZN":  ("아마존",         "Amazon"),
    "GOOGL": ("구글",           "Google"),
    "META":  ("메타",           "Meta"),
    "TSLA":  ("테슬라",         "Tesla"),
    "AVGO":  ("브로드컴",       "Broadcom"),
    "COST":  ("코스트코",       "Costco"),
    "NFLX":  ("넷플릭스",       "Netflix"),
}

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DELAY = 1.0


def _parse_date(published: str | None) -> date:
    if published:
        try:
            return parsedate_to_datetime(published).date()
        except Exception:
            pass
    return datetime.now().date()


def _fetch_google_news_rss(query: str) -> list[feedparser.FeedParserDict]:
    """Google News RSS로 한국어 뉴스 검색."""
    url = f"{GOOGLE_NEWS_RSS}?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return feed.entries
    except Exception as e:
        logger.warning("[us_news] %s 검색 실패: %s", query, e)
        return []


def collect_us_news(cutoff_date: date | None = None) -> int:
    """
    미국 종목 10개 뉴스 수집 후 DB 저장.

    Args:
        cutoff_date: 이 날짜 이후 기사만 수집 (None이면 전체)

    Returns:
        저장된 언급 건수
    """
    records: list[dict] = []

    for ticker, (kr_query, en_name) in US_STOCK_QUERIES.items():
        entries = _fetch_google_news_rss(kr_query)
        ticker_count = 0

        for entry in entries:
            title   = entry.get("title", "")
            summary = entry.get("summary", "")
            link    = entry.get("link", "") or entry.get("id", "")
            if not link:
                continue

            art_date = _parse_date(entry.get("published"))
            if cutoff_date and art_date < cutoff_date:
                continue

            text = title + " " + summary
            sentiment = analyze_sentiment(text)

            records.append({
                "ticker":       ticker,
                "mentioned_at": art_date.isoformat(),
                "source":       "naver",
                "doc_id":       link[:500],
                "sentiment":    sentiment,
            })
            ticker_count += 1

        logger.info("[us_news] %s(%s): %d건", ticker, kr_query, ticker_count)
        time.sleep(DELAY)

    # 중복 제거 (doc_id + ticker)
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in records:
        key = (r["doc_id"], r["ticker"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if not deduped:
        logger.info("[us_news] 수집 결과 없음")
        return 0

    saved = upsert_mentions(deduped)
    logger.info("[us_news] 총 %d건 저장", saved)
    return saved


def collect_us_news_backfill(days: int = 90) -> int:
    """cutoff 없이 전체 수집 (Google News는 약 7일치만 제공)."""
    return collect_us_news(cutoff_date=None)
