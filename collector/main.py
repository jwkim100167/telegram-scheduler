"""
불타기 투자 대시보드 - 수집기 CLI 진입점

사용법:
  python -m collector.main collect        # DART RSS 수집
  python -m collector.main collect-board  # 네이버 종목토론방 수집 (페이지 수 지정 가능)
  python -m collector.main aggregate      # 주간 섹터 집계
  python -m collector.main monthly        # 월간 종목 집계
  python -m collector.main age            # 에이징 (raw -> archived)
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def cmd_collect() -> None:
    from collector.matcher.keyword_matcher import KeywordMatcher
    from collector.sources.dart_rss import collect_dart
    from collector.sources.naver_news import collect_news
    from collector.sources.naver_research import collect_naver_research

    matcher = KeywordMatcher()
    matcher.load_from_supabase()

    total = 0
    total += collect_dart(matcher)
    total += collect_news(matcher)
    total += collect_naver_research(matcher)
    logger.info("전체 수집 완료: %d건", total)


def cmd_collect_us() -> None:
    """미국 NASDAQ Top10 종목 뉴스 수집 (Google News RSS)."""
    from collector.sources.us_news_search import collect_us_news
    collect_us_news()


def cmd_aggregate() -> None:
    from collector.aggregator import run_weekly_aggregate
    run_weekly_aggregate()


def cmd_monthly() -> None:
    from collector.aggregator import run_monthly_aggregate
    run_monthly_aggregate()


def cmd_age() -> None:
    from collector.aggregator import run_aging
    run_aging()


def cmd_backfill() -> None:
    """최근 N일 데이터 백필. 기본 14일, 인수로 일수 지정 가능.

    예: python -m collector.main backfill 91  (13주)
    """
    from datetime import datetime, timedelta
    from collector.matcher.keyword_matcher import KeywordMatcher
    from collector.sources.dart_rss import collect_dart_range
    from collector.sources.naver_research import collect_naver_research_backfill

    days = int(sys.argv[2]) if len(sys.argv) > 2 else 14

    matcher = KeywordMatcher()
    matcher.load_from_supabase()

    today = datetime.now().date()
    total = 0

    logger.info("=== DART 백필 시작 (%d일) ===", days)
    for i in range(days, 0, -1):
        target = today - timedelta(days=i)
        date_str = target.strftime("%Y%m%d")
        count = collect_dart_range(matcher, bgn_de=date_str, end_de=date_str)
        logger.info("%s DART: %d건", target, count)
        total += count

    logger.info("=== 네이버 리서치 백필 시작 (%d일) ===", days)
    total += collect_naver_research_backfill(matcher, days=days)

    logger.info("백필 완료: 총 %d건", total)


def cmd_fetch_prices() -> None:
    """주간 섹터 수익률 수집 후 weekly_sector_returns에 저장.
    인수 없으면 최근 4주, 숫자 지정 가능.

    예: python -m collector.main fetch-prices 106  (전체 2년)
    """
    from collector.sources.price_fetcher import fetch_and_save_sector_returns
    weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    fetch_and_save_sector_returns(weeks=weeks)


def cmd_fetch_benchmarks() -> None:
    """코스피200/코스닥150 벤치마크 주간 수익률 수집.
    인수 없으면 최근 4주, 숫자 지정 가능.

    예: python -m collector.main fetch-benchmarks 106
    """
    from collector.sources.price_fetcher import fetch_and_save_benchmark_returns
    weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    fetch_and_save_benchmark_returns(weeks=weeks)


def cmd_collect_board() -> None:
    """네이버 종목토론방 수집.
    인수 없으면 1페이지(15건), 숫자 지정 가능.

    예: python -m collector.main collect-board 3  (3페이지 × 전 종목)
    """
    from collector.sources.naver_board import collect_board
    from collector.db.supabase_client import get_client, upsert_mentions

    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    client = get_client()

    rows = client.table("stocks").select("ticker").execute().data
    tickers = [r["ticker"] for r in rows]

    logger.info("종목토론방 수집 시작: %d종목 × %d페이지", len(tickers), pages)
    records = collect_board(tickers, pages=pages)

    # (doc_id, ticker) 중복 제거
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in records:
        key = (r["doc_id"], r["ticker"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    logger.info("[board] 수집 %d건 → 중복 제거 후 %d건", len(records), len(deduped))

    saved = upsert_mentions(deduped)
    logger.info("[board] %d건 upsert 완료", saved)


def cmd_full_backfill() -> None:
    """리포트 백필 → 집계 → 섹터 주가 → 벤치마크를 한 번에 실행.
    인수로 시작 연도 지정 (기본 2018).

    예: python -m collector.main full-backfill 2018
        python -m collector.main full-backfill 2023
    """
    from datetime import datetime
    from collector.matcher.keyword_matcher import KeywordMatcher
    from collector.sources.naver_research import collect_naver_research_backfill
    from collector.aggregator import run_weekly_aggregate
    from collector.sources.price_fetcher import (
        fetch_and_save_sector_returns,
        fetch_and_save_benchmark_returns,
    )

    start_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2018
    start_date = datetime(start_year, 1, 1)
    days  = (datetime.now() - start_date).days
    weeks = days // 7 + 10  # 여유분 포함

    logger.info("=== full-backfill 시작: %d년 이후 (%d일 / %d주) ===", start_year, days, weeks)

    # 1) 리포트 백필
    logger.info("--- [1/4] 네이버 리서치 백필 ---")
    matcher = KeywordMatcher()
    matcher.load_from_supabase()
    collect_naver_research_backfill(matcher, days=days)

    # 2) 주간 집계
    logger.info("--- [2/4] 주간 섹터 집계 ---")
    run_weekly_aggregate()

    # 3) 섹터 주가 수익률
    logger.info("--- [3/4] 섹터 주가 수익률 수집 (%d주) ---", weeks)
    fetch_and_save_sector_returns(weeks=weeks)

    # 4) 벤치마크 수익률
    logger.info("--- [4/4] 벤치마크 수익률 수집 (%d주) ---", weeks)
    fetch_and_save_benchmark_returns(weeks=weeks)

    logger.info("=== full-backfill 완료 ===")


def cmd_fetch_prices_fdr() -> None:
    """FDR로 역사적 섹터/벤치마크 주가 수익률 수집 (네이버 API 한계 극복).
    인수로 시작 연도 지정 (기본 2018).

    예: python -m collector.main fetch-prices-fdr 2018
    """
    from collector.sources.price_fetcher import (
        fetch_historical_sector_returns_fdr,
        fetch_historical_benchmark_returns_fdr,
    )
    start_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2018
    start_date = f"{start_year}-01-01"
    logger.info("=== FDR 역사적 가격 수집 시작 (%s 이후) ===", start_date)
    logger.info("--- [1/2] 섹터 수익률 ---")
    fetch_historical_sector_returns_fdr(start_date)
    logger.info("--- [2/2] 벤치마크 수익률 ---")
    fetch_historical_benchmark_returns_fdr(start_date)
    logger.info("=== FDR 역사적 가격 수집 완료 ===")


def cmd_seed_krx() -> None:
    """pykrx 시총 상위 500종목 자동 시드 (종목 추가/제거 반영)"""
    from collector.db.seed_krx import seed_krx
    seed_krx()


def cmd_debug_dart() -> None:
    """DART RSS 원문 5개 출력 (매칭 디버그용)"""
    import feedparser
    feed = feedparser.parse("https://opendart.fss.or.kr/api/rss.xml")
    print(f"총 항목 수: {len(feed.entries)}")
    for entry in feed.entries[:5]:
        print("---")
        print(f"title  : {entry.get('title', '')}")
        print(f"summary: {entry.get('summary', '')[:100]}")
        print(f"id     : {entry.get('id', '')}")


COMMANDS = {
    "collect":        cmd_collect,
    "collect-us":     cmd_collect_us,
    "collect-board":  cmd_collect_board,
    "aggregate":      cmd_aggregate,
    "monthly":    cmd_monthly,
    "age":        cmd_age,
    "backfill":   cmd_backfill,
    "fetch-prices":      cmd_fetch_prices,
    "fetch-benchmarks":  cmd_fetch_benchmarks,
    "full-backfill":    cmd_full_backfill,
    "fetch-prices-fdr": cmd_fetch_prices_fdr,
    "seed-krx":   cmd_seed_krx,
    "debug-dart": cmd_debug_dart,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"사용법: python -m collector.main [{' | '.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
