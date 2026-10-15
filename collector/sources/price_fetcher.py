"""
네이버 금융 주간 OHLCV API로 섹터별 주간 수익률을 수집해 weekly_sector_returns에 저장.

수익률 계산:
  - 해당 주 시가(open) → 종가(close) 수익률: (close - open) / open * 100
  - 각 섹터 내 유효 종목의 등가중 평균
  - 종목당 1 API 호출로 2년치를 한 번에 가져옴
"""

import logging
import time
from datetime import datetime, timedelta

import requests

from collector.db.supabase_client import get_client

logger = logging.getLogger(__name__)

NAVER_CHART_URL = "https://fchart.stock.naver.com/sise.nhn"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _fetch_weekly_prices(ticker: str, count: int = 120) -> dict[str, dict]:
    """
    네이버 금융에서 ticker의 주간 OHLCV를 가져온다.
    반환: {날짜(YYYYMMDD): {"open": int, "close": int}}
    날짜는 해당 주의 금요일 기준.
    """
    params = {
        "symbol": ticker,
        "timeframe": "week",
        "count": count,
        "requestType": 0,
    }
    try:
        r = requests.get(NAVER_CHART_URL, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.debug("%s 조회 실패: %s", ticker, e)
        return {}

    result: dict[str, dict] = {}
    for line in r.text.splitlines():
        if "<item data=" not in line:
            continue
        # data="20240610|284500|299500|262000|270500|190172616"
        raw = line.split('"')[1]
        parts = raw.strip("|").split("|")
        if len(parts) < 5:
            continue
        date_str, open_str, _, _, close_str, *_ = parts
        try:
            result[date_str] = {"open": int(open_str), "close": int(close_str)}
        except ValueError:
            continue
    return result


def fetch_and_save_sector_returns(weeks: int = 4) -> None:
    """최근 N주의 주간 섹터 수익률을 수집해 weekly_sector_returns에 저장."""
    client = get_client()

    # 1) ticker → sector_id 매핑
    stocks_res = client.table("stocks").select("ticker,sector_id").execute()
    ticker_sector: dict[str, str] = {
        r["ticker"]: r["sector_id"] for r in stocks_res.data if r["sector_id"]
    }

    # 2) 대상 주 목록 (weekly_sector_stats 기준, 페이지네이션)
    cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    all_stat_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("weekly_sector_stats")
            .select("week_start")
            .gte("week_start", cutoff)
            .order("week_start")
            .range(offset, offset + 999)
            .execute()
        )
        all_stat_rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    target_weeks = sorted(set(r["week_start"] for r in all_stat_rows))
    if not target_weeks:
        logger.warning("집계된 주간 데이터 없음")
        return

    logger.info("대상 주: %d개 (%s ~ %s)", len(target_weeks), target_weeks[0], target_weeks[-1])

    # 3) 주 → 네이버 금요일 날짜 매핑 (week_start = 월요일, +4 = 금요일)
    week_to_fri: dict[str, str] = {}
    for w in target_weeks:
        mon = datetime.strptime(w, "%Y-%m-%d")
        fri = mon + timedelta(days=4)
        week_to_fri[w] = fri.strftime("%Y%m%d")

    # 4) 종목별 주간 OHLCV 수집 → 섹터별 수익률 집계
    # sector_week_returns[week_start][sector_id] = [ret, ...]
    sector_week_returns: dict[str, dict[str, list[float]]] = {
        w: {} for w in target_weeks
    }

    tickers = list(ticker_sector.keys())
    logger.info("주가 수집 시작: %d종목", len(tickers))

    for i, ticker in enumerate(tickers):
        price_data = _fetch_weekly_prices(ticker, count=max(weeks + 10, 120))
        sid = ticker_sector[ticker]

        for w, fri_str in week_to_fri.items():
            # 금요일 데이터 탐색 (±3거래일 허용)
            mon = datetime.strptime(w, "%Y-%m-%d")
            ohlcv = None
            for delta in [0, -1, 1, -2, 2, -3, 3]:
                candidate = (mon + timedelta(days=4 + delta)).strftime("%Y%m%d")
                if candidate in price_data:
                    ohlcv = price_data[candidate]
                    break

            if ohlcv and ohlcv["open"] > 0:
                ret = (ohlcv["close"] - ohlcv["open"]) / ohlcv["open"] * 100
                sector_week_returns[w].setdefault(sid, []).append(ret)

        if (i + 1) % 50 == 0:
            logger.info("  %d/%d 종목 처리", i + 1, len(tickers))
        time.sleep(0.05)  # 과도한 요청 방지

    # 5) Supabase upsert
    rows: list[dict] = []
    for w, sector_map in sector_week_returns.items():
        for sid, rets in sector_map.items():
            if not rets:
                continue
            rows.append({
                "week_start":  w,
                "sector_id":   sid,
                "return_pct":  round(sum(rets) / len(rets), 4),
                "stock_count": len(rets),
            })

    if rows:
        BATCH = 200
        for i in range(0, len(rows), BATCH):
            client.table("weekly_sector_returns").upsert(
                rows[i:i+BATCH], on_conflict="week_start,sector_id"
            ).execute()
        logger.info("upsert 완료: %d행", len(rows))

    print(f"\n완료: {len(target_weeks)}주 × 섹터별 수익률 {len(rows)}행 저장")


# 섹터별 대표 ETF 매핑 (없는 섹터는 등가중 평균 fallback)
SECTOR_ETF_MAP: dict[str, str] = {
    'SEMICONDUCTOR': '091160',  # KODEX 반도체
    'BATTERY':       '305720',  # KODEX 2차전지산업
    'BIOTECH':       '244580',  # KODEX 바이오
    'AUTO':          '091180',  # KODEX 자동차
    'STEEL':         '139230',  # KODEX 철강
    'FINANCE':       '139270',  # KODEX 금융
    'CHEMICAL':      '139220',  # KODEX 화학
    'IT':            '266360',  # KODEX IT
    'CONSTRUCTION':  '139240',  # KODEX 건설
    'SHIPBUILDING':  '466920',  # SOL 조선TOP3플러스 (2023-10 상장, 이전 주는 return=0)
    'DEFENSE':       '449450',  # PLUS K방산 (2023-01 상장, 이전 주는 return=0)
    'NASDAQ_TOP10':  'QQQ',     # Invesco QQQ Trust (NASDAQ 100 ETF, FDR US ETF 지원)
}


def _get_target_weeks(client, start_date: str) -> list[str]:
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("weekly_sector_stats")
            .select("week_start")
            .gte("week_start", start_date)
            .order("week_start")
            .range(offset, offset + 999)
            .execute()
        )
        all_rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    return sorted(set(r["week_start"] for r in all_rows))


def _weekly_returns_from_fdr(fdr, ticker: str, start_date: str, target_set: set[str]) -> dict[str, float]:
    """FDR에서 ticker의 주간 수익률 딕셔너리 반환. 데이터 없는 주는 포함 안 함."""
    result: dict[str, float] = {}
    try:
        df = fdr.DataReader(ticker, start_date)
        if df.empty:
            return result
        weekly = df.resample("W-MON", closed="left", label="left").agg(
            {"Open": "first", "Close": "last"}
        ).dropna()
        for idx_date, row in weekly.iterrows():
            w = idx_date.strftime("%Y-%m-%d")
            if w in target_set and row["Open"] > 0:
                result[w] = (row["Close"] - row["Open"]) / row["Open"] * 100
    except Exception as e:
        logger.debug("%s 수집 실패: %s", ticker, e)
    return result


def fetch_historical_sector_returns_fdr(start_date: str = "2018-01-01") -> None:
    """FinanceDataReader로 역사적 섹터 주가 수익률을 수집해 weekly_sector_returns에 저장.

    - SECTOR_ETF_MAP에 있는 섹터: 대표 ETF 수익률 사용
      (ETF 상장 전 주는 return_pct=0 으로 저장 → 현상유지)
    - 나머지 섹터: 구성 종목 등가중 평균
    """
    try:
        import FinanceDataReader as fdr
    except ImportError:
        logger.error("FinanceDataReader 미설치: pip install finance-datareader")
        return

    client = get_client()

    # 대상 주 목록
    target_weeks = _get_target_weeks(client, start_date)
    if not target_weeks:
        logger.warning("대상 주 없음")
        return
    target_set = set(target_weeks)
    logger.info("FDR 섹터 수익률 수집 시작 (%s 이후, %d주)", start_date, len(target_weeks))

    # sector_id → {week_start: return_pct}
    result: dict[str, dict[str, float]] = {}

    # ── 1) ETF 맵 섹터: ETF 수익률 사용 ──────────────────────────
    logger.info("--- ETF 기반 섹터 (%d개) ---", len(SECTOR_ETF_MAP))
    for sid, etf_ticker in SECTOR_ETF_MAP.items():
        etf_rets = _weekly_returns_from_fdr(fdr, etf_ticker, start_date, target_set)
        result[sid] = {}
        for w in target_weeks:
            # ETF 데이터 없는 주(상장 전) → 0 (현상유지)
            result[sid][w] = etf_rets.get(w, 0.0)
        logger.info("  %s (%s): %d주 ETF 데이터", sid, etf_ticker, len(etf_rets))
        time.sleep(0.1)

    # ── 2) 나머지 섹터: 구성 종목 등가중 평균 ──────────────────────
    etf_sectors = set(SECTOR_ETF_MAP.keys())
    stocks_res = client.table("stocks").select("ticker,sector_id").execute()
    ticker_sector: dict[str, str] = {
        r["ticker"]: r["sector_id"]
        for r in stocks_res.data
        if r["sector_id"] and r["sector_id"] not in etf_sectors
    }
    logger.info("--- 등가중 섹터: %d종목 ---", len(ticker_sector))

    # week → sector → [ret, ...]
    avg_buf: dict[str, dict[str, list[float]]] = {w: {} for w in target_weeks}
    for i, (ticker, sid) in enumerate(ticker_sector.items()):
        rets = _weekly_returns_from_fdr(fdr, ticker, start_date, target_set)
        for w, ret in rets.items():
            avg_buf[w].setdefault(sid, []).append(ret)
        if (i + 1) % 50 == 0:
            logger.info("  %d/%d 종목 처리", i + 1, len(ticker_sector))
        time.sleep(0.05)

    for w, sector_map in avg_buf.items():
        for sid, rets in sector_map.items():
            if rets:
                result.setdefault(sid, {})[w] = sum(rets) / len(rets)

    # ── 3) Supabase upsert ────────────────────────────────────────
    rows: list[dict] = []
    for sid, week_map in result.items():
        for w, ret in week_map.items():
            rows.append({
                "week_start":  w,
                "sector_id":   sid,
                "return_pct":  round(ret, 4),
                "stock_count": 1 if sid in etf_sectors else 0,
            })
    if rows:
        BATCH = 200
        for i in range(0, len(rows), BATCH):
            client.table("weekly_sector_returns").upsert(
                rows[i:i+BATCH], on_conflict="week_start,sector_id"
            ).execute()
    logger.info("FDR 섹터 수익률 upsert 완료: %d행", len(rows))


def fetch_historical_benchmark_returns_fdr(start_date: str = "2018-01-01") -> None:
    """FinanceDataReader로 역사적 KOSPI200/KOSDAQ150 벤치마크 수익률 저장."""
    try:
        import FinanceDataReader as fdr
    except ImportError:
        logger.error("FinanceDataReader 미설치: pip install finance-datareader")
        return

    client = get_client()

    # 대상 주 목록
    all_stat_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("weekly_sector_stats")
            .select("week_start")
            .gte("week_start", start_date)
            .order("week_start")
            .range(offset, offset + 999)
            .execute()
        )
        all_stat_rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    target_weeks = sorted(set(r["week_start"] for r in all_stat_rows))
    target_set = set(target_weeks)
    if not target_weeks:
        logger.warning("대상 주 없음")
        return

    bench_map = {"kospi200_ret": "069500", "kosdaq150_ret": "229200"}
    bench_data: dict[str, dict[str, float]] = {col: {} for col in bench_map}

    for col, ticker in bench_map.items():
        try:
            df = fdr.DataReader(ticker, start_date)
            if df.empty:
                continue
            weekly = df.resample("W-MON", closed="left", label="left").agg(
                {"Open": "first", "Close": "last"}
            ).dropna()
            for idx_date, row in weekly.iterrows():
                w = idx_date.strftime("%Y-%m-%d")
                if w not in target_set or row["Open"] <= 0:
                    continue
                bench_data[col][w] = round((row["Close"] - row["Open"]) / row["Open"] * 100, 4)
            logger.info("%s (%s): %d주 수집", col, ticker, len(bench_data[col]))
        except Exception as e:
            logger.error("%s 수집 실패: %s", ticker, e)
        time.sleep(0.1)

    rows: list[dict] = []
    for w in target_weeks:
        row: dict = {"week_start": w}
        for col in bench_map:
            row[col] = bench_data[col].get(w)
        if any(row[col] is not None for col in bench_map):
            rows.append(row)

    if rows:
        BATCH = 200
        for i in range(0, len(rows), BATCH):
            client.table("weekly_benchmark_returns").upsert(
                rows[i:i+BATCH], on_conflict="week_start"
            ).execute()
    logger.info("FDR 벤치마크 upsert 완료: %d행", len(rows))


# KODEX200 = 코스피200 ETF, KODEX KOSDAQ150 = 코스닥150 ETF
BENCHMARKS = {
    "kospi200_ret":  "069500",
    "kosdaq150_ret": "229200",
}


def fetch_and_save_benchmark_returns(weeks: int = 4) -> None:
    """최근 N주의 코스피/코스닥 벤치마크 주간 수익률을 수집해 weekly_benchmark_returns에 저장."""
    client = get_client()

    # 대상 주 목록 (weekly_sector_stats 기준)
    cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    all_stat_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            client.table("weekly_sector_stats")
            .select("week_start")
            .gte("week_start", cutoff)
            .order("week_start")
            .range(offset, offset + 999)
            .execute()
        )
        all_stat_rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    target_weeks = sorted(set(r["week_start"] for r in all_stat_rows))
    if not target_weeks:
        logger.warning("대상 주 없음")
        return

    logger.info("벤치마크 수집 대상 주: %d개", len(target_weeks))

    # 주 → 금요일 날짜 매핑
    week_to_fri: dict[str, str] = {}
    for w in target_weeks:
        mon = datetime.strptime(w, "%Y-%m-%d")
        week_to_fri[w] = (mon + timedelta(days=4)).strftime("%Y%m%d")

    # 벤치마크 ETF 별로 주간 OHLCV 수집
    bench_data: dict[str, dict[str, float]] = {col: {} for col in BENCHMARKS}
    for col, ticker in BENCHMARKS.items():
        price_data = _fetch_weekly_prices(ticker, count=max(weeks + 10, 120))
        for w in target_weeks:
            mon = datetime.strptime(w, "%Y-%m-%d")
            ohlcv = None
            for delta in [0, -1, 1, -2, 2, -3, 3]:
                candidate = (mon + timedelta(days=4 + delta)).strftime("%Y%m%d")
                if candidate in price_data:
                    ohlcv = price_data[candidate]
                    break
            if ohlcv and ohlcv["open"] > 0:
                bench_data[col][w] = round(
                    (ohlcv["close"] - ohlcv["open"]) / ohlcv["open"] * 100, 4
                )
        time.sleep(0.1)
        logger.info("  %s (%s) 수집 완료: %d주", col, ticker, len(bench_data[col]))

    rows: list[dict] = []
    for w in target_weeks:
        row: dict = {"week_start": w}
        for col in BENCHMARKS:
            row[col] = bench_data[col].get(w)
        if any(row[col] is not None for col in BENCHMARKS):
            rows.append(row)

    if rows:
        BATCH = 200
        for i in range(0, len(rows), BATCH):
            client.table("weekly_benchmark_returns").upsert(
                rows[i : i + BATCH], on_conflict="week_start"
            ).execute()
        logger.info("벤치마크 upsert 완료: %d행", len(rows))

    print(f"\n완료: {len(rows)}주 벤치마크 수익률(KOSPI200/KOSDAQ150) 저장")
