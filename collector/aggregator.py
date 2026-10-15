"""
집계 레이어: raw_mentions -> weekly_sector_stats / monthly_stock_stats
에이징: raw_mentions -> archived_mentions (13주 초과)
"""

import logging
from collector.db.supabase_client import get_client
from collector.config import AGING_WEEKS

logger = logging.getLogger(__name__)


def run_weekly_aggregate() -> None:
    """이번 주 섹터별 언급 수를 집계해 weekly_sector_stats 에 upsert."""
    client = get_client()
    # Supabase rpc 로 SQL 함수 호출 (함수는 Supabase DB에 미리 등록)
    client.rpc("upsert_weekly_sector_stats").execute()
    logger.info("주간 섹터 집계 완료")


def run_monthly_aggregate() -> None:
    """이번 달 종목별 언급 수를 집계해 monthly_stock_stats 에 upsert."""
    client = get_client()
    client.rpc("upsert_monthly_stock_stats").execute()
    logger.info("월간 종목 집계 완료")


def run_aging() -> None:
    """AGING_WEEKS 초과 raw_mentions 를 archived_mentions 로 이동."""
    client = get_client()
    client.rpc("archive_old_mentions", {"weeks": AGING_WEEKS}).execute()
    logger.info("에이징 처리 완료 (기준: %d주)", AGING_WEEKS)
