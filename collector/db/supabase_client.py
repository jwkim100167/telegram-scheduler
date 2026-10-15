from functools import lru_cache
from supabase import create_client, Client
from collector.config import SUPABASE_URL, SUPABASE_SERVICE_KEY


@lru_cache(maxsize=1)
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def upsert_mentions(records: list[dict]) -> int:
    """raw_mentions 에 upsert. 중복(doc_id, ticker)은 무시."""
    if not records:
        return 0
    client = get_client()
    client.table("raw_mentions").upsert(
        records,
        on_conflict="doc_id,ticker",
    ).execute()
    return len(records)


def fetch_stocks() -> list[dict]:
    """stocks 테이블 전체 조회 (ticker, name, aliases)."""
    client = get_client()
    res = client.table("stocks").select("ticker,name,aliases").execute()
    return res.data or []
