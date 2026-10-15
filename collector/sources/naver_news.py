"""
국내 경제지 RSS 수집기 (API 키 불필요).

한국경제, 매일경제, 연합뉴스 경제 RSS를 파싱해
종목명을 매칭하고 raw_mentions 에 적재한다.
"""

import logging
from datetime import date, datetime
from email.utils import parsedate_to_datetime

import re

import feedparser
import requests

from collector.db.supabase_client import upsert_mentions
from collector.matcher.keyword_matcher import KeywordMatcher
from collector.sources.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    ("chosunbiz", "https://biz.chosun.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("mk",        "https://www.mk.co.kr/rss/40300001/"),
    ("yna",       "https://www.yna.co.kr/rss/economy.xml"),
]


def _parse_date(published: str | None) -> date:
    if published:
        try:
            return parsedate_to_datetime(published).date()
        except Exception:
            pass
    return datetime.now().date()


def _fetch_rss(url: str) -> str:
    """RSS 원문을 가져와 undefined entity를 제거한다."""
    resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    # XML에서 허용되지 않는 HTML 엔티티 제거 (&nbsp; &amp; 등 표준 외)
    text = resp.text
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)(\w+);", "", text)
    return text


def _collect_one(source_id: str, url: str, matcher: KeywordMatcher) -> list[dict]:
    logger.info("%s RSS 수집 중: %s", source_id, url)
    try:
        raw = _fetch_rss(url)
        feed = feedparser.parse(raw)
    except Exception as e:
        logger.warning("%s RSS 요청 실패, URL 직접 파싱 시도: %s", source_id, e)
        feed = feedparser.parse(url)

    if feed.bozo:
        logger.warning("%s RSS 파싱 경고: %s", source_id, feed.bozo_exception)

    records: list[dict] = []
    for entry in feed.entries:
        text = entry.get("title", "") + " " + entry.get("summary", "")
        doc_id = entry.get("id") or entry.get("link", "")
        if not doc_id:
            continue

        mentioned_at = _parse_date(entry.get("published"))
        sentiment = analyze_sentiment(text)
        for ticker in matcher.match(text):
            records.append({
                "mentioned_at": mentioned_at.isoformat(),
                "ticker": ticker,
                "source": "naver",
                "doc_id": doc_id,
                "sentiment": sentiment,
            })

    logger.info("%s: %d건 매칭", source_id, len(records))
    return records


def collect_news(matcher: KeywordMatcher) -> int:
    all_records: list[dict] = []
    for source_id, url in RSS_SOURCES:
        try:
            all_records.extend(_collect_one(source_id, url, matcher))
        except Exception as e:
            logger.error("%s 수집 실패: %s", source_id, e)

    count = upsert_mentions(all_records)
    logger.info("뉴스 RSS 수집 완료: 총 %d건 처리", count)
    return count
