"""
CSV 초기 데이터를 Supabase에 적재한다.
실행: python -m collector.db.seed

실행 전 .env 에 SUPABASE_URL, SUPABASE_SERVICE_KEY 가 설정돼 있어야 한다.
"""

import csv
import pathlib
from collector.db.supabase_client import get_client

DATA_DIR = pathlib.Path(__file__).parents[2] / "data"


def seed_sectors(client) -> None:
    rows = _read_csv("sectors.csv")
    client.table("sectors").upsert(rows, on_conflict="sector_id").execute()
    print(f"  섹터 {len(rows)}개 적재 완료")


def seed_stocks(client) -> None:
    rows = _read_csv("stocks.csv")
    for row in rows:
        # aliases 컬럼: CSV에서 "삼전,삼성전자우" -> ["삼전", "삼성전자우"]
        raw = row.get("aliases", "")
        row["aliases"] = [a.strip() for a in raw.split(",") if a.strip()] if raw else []
    client.table("stocks").upsert(rows, on_conflict="ticker").execute()
    print(f"  종목 {len(rows)}개 적재 완료")


def _read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    client = get_client()
    print("Supabase 시드 시작...")
    seed_sectors(client)
    seed_stocks(client)
    print("완료.")
