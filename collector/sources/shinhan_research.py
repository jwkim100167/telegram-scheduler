"""
신한투자증권 리서치 수집기.

모바일 API 엔드포인트에서 리포트 목록을 받아
제목에서 종목명을 매칭한다. PDF 다운로드 없이 동작.
"""

import logging
from datetime import date, datetime

import requests

from collector.db.supabase_client import upsert_mentions
from collector.matcher.keyword_matcher import KeywordMatcher

logger = logging.getLogger(__name__)

API_URL = "https://m.shinhansec.com/mweb/api/invt/shrh/ishrhShrhList"
BBS_NAME = (
    "giperiodicaldaily|gistockchart|plananalysis|gicompanyanalyst"
    "|giindustry|gieconomy|fxmarket|commodity|gibond|foreignbond"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Referer": "https://m.shinhansec.com/",
}


def _parse_date(date_str: str | None) -> date:
    """'20260605080107' (YYYYMMDDHHmmss) -> date. 앞 8자리만 사용."""
    if date_str and len(date_str) >= 8:
        try:
            return datetime.strptime(date_str[:8], "%Y%m%d").date()
        except ValueError:
            pass
    return datetime.now().date()


def collect_shinhan(matcher: KeywordMatcher) -> int:
    logger.info("신한투자증권 리서치 수집 시작")

    payload = {
        "url": "/mweb/api/invt/shrh/ishrhShrhList",
        "callbackFun": "ishrh1001.tab1_callbackFun",
        "bbs_name": BBS_NAME,
        "curPage": 1,
        "lastPageFlag": "true",
        "repeatKeyN": "",
        "repeatKeyP": "",
        "tran": False,
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("신한 리서치 API 요청 실패: %s", e)
        return 0

    # body.list01.outputList 구조
    try:
        items = data["body"]["list01"]["outputList"]
    except (KeyError, TypeError):
        logger.warning("신한 리서치: 응답 구조 오류. 키: %s", list(data.keys()))
        return 0

    logger.info("신한 리서치 %d건 수신", len(items))

    records: list[dict] = []
    for item in items:
        title: str = item.get("title", "")
        if not title:
            continue

        # date: "20260605080107" (YYYYMMDDHHmmss)
        mentioned_at = _parse_date(item.get("date"))

        # doc_id: bbs_name + message_id 조합으로 고유성 보장
        doc_id = f"shinhan:{item.get('bbs_name')}:{item.get('message_id')}"

        tickers = matcher.match(title)
        for ticker in tickers:
            records.append({
                "mentioned_at": mentioned_at.isoformat(),
                "ticker": ticker,
                "source": "report",
                "doc_id": doc_id,
            })

    count = upsert_mentions(records)
    logger.info("신한 리서치 수집 완료: %d건 처리", count)
    return count
