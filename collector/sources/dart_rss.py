"""
DART OpenAPI 공시 수집기.

DART OpenAPI list 엔드포인트에서 최근 공시 목록을 받아
종목명을 매칭하고 raw_mentions 테이블에 적재한다.

API 키 발급: https://opendart.fss.or.kr
"""

import logging
from datetime import date, datetime

import requests

from collector.config import DART_API_KEY
from collector.db.supabase_client import upsert_mentions
from collector.matcher.keyword_matcher import KeywordMatcher
from collector.sources.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def _parse_date(date_str: str | None) -> date:
    """'20240101' 형식 -> date. 실패 시 오늘."""
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            pass
    return datetime.now().date()


def _fetch_dart(matcher: KeywordMatcher, bgn_de: str | None = None, end_de: str | None = None) -> list[dict]:
    """DART API 호출 후 매칭된 records 반환."""
    params: dict = {
        "crtfc_key": DART_API_KEY,
        "page_no": 1,
        "page_count": 100,
    }
    if bgn_de:
        params["bgn_de"] = bgn_de
    if end_de:
        params["end_de"] = end_de

    response = requests.get(DART_LIST_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "000":
        logger.error("DART API 오류: %s %s", data.get("status"), data.get("message"))
        return []

    items = data.get("list", [])
    records: list[dict] = []
    for item in items:
        text = item.get("corp_name", "") + " " + item.get("report_nm", "")
        doc_id: str = item.get("rcept_no", "")
        if not doc_id:
            continue
        mentioned_at = _parse_date(item.get("rcept_dt"))
        sentiment = analyze_sentiment(text)
        for ticker in matcher.match(text):
            records.append({
                "mentioned_at": mentioned_at.isoformat(),
                "ticker": ticker,
                "source": "dart",
                "doc_id": doc_id,
                "sentiment": sentiment,
            })
    return records


def collect_dart(matcher: KeywordMatcher) -> int:
    """DART OpenAPI에서 최근 공시를 수집해 raw_mentions에 적재한다."""
    logger.info("DART OpenAPI 수집 시작")
    records = _fetch_dart(matcher)
    logger.info("DART 공시 %d건 매칭", len(records))
    count = upsert_mentions(records)
    logger.info("DART 수집 완료: %d건 처리", count)
    return count


def collect_dart_range(matcher: KeywordMatcher, bgn_de: str, end_de: str) -> int:
    """날짜 범위로 DART 공시 수집."""
    logger.info("DART 기간 수집: %s ~ %s", bgn_de, end_de)
    records = _fetch_dart(matcher, bgn_de=bgn_de, end_de=end_de)
    logger.info("DART %s~%s: %d건 매칭", bgn_de, end_de, len(records))
    count = upsert_mentions(records)
    return count
