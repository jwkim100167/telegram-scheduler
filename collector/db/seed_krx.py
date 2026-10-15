"""
FinanceDataReader 를 사용해 코스피+코스닥 시총 상위 500종목을 자동으로 Supabase에 적재한다.

실행: python -m collector.db.seed_krx

- 매번 실행 시 최신 시총 기준으로 상위 500종목을 upsert
- KRX 업종 코드(INDUSTRY_MAP)를 1차로 사용, 투자 테마(THEME_HINTS)가 우선 적용
- 500위 밖으로 밀린 종목은 raw_mentions 참조 없을 때만 삭제
"""

import logging
import sys

from collector.db.supabase_client import get_client

logger = logging.getLogger(__name__)

STOCK_LIMIT = 500

# ── 1순위: 투자 테마 키워드 (이름 기반, 업종 분류보다 우선) ──────────────────
# 업종 코드가 넓어서 테마가 묻히는 경우를 방지
THEME_HINTS: list[tuple[list[str], str]] = [
    # 지주·그룹 모회사 → ETC (사업 섹터 미분류, 가장 먼저 체크)
    # ※ 사업회사(SK하이닉스, LG화학 등)는 아래 항목에서 먼저 잡힘
    #   여기서는 종목명이 짧고 단독 지주사인 경우만 명시
    (["SK스퀘어", "SK홀딩스", "LG홀딩스", "CJ홀딩스", "GS홀딩스", "LS홀딩스",
      "HD현대", "HDC홀딩스", "효성홀딩스", "한화홀딩스", "롯데지주", "포스코홀딩스",
      "OCI홀딩스", "코오롱홀딩스", "삼양홀딩스", "세아홀딩스", "쿠쿠홀딩스",
      "영풍홀딩스", "오리온홀딩스"], "ETC"),
    # 두산 그룹 명시 고정 (전기전자 업종 오분류 방지)
    (["두산에너빌리티", "두산퓨얼셀"], "ENERGY"),
    (["두산로보틱스"], "INDUSTRIAL"),
    (["두산"], "ETC"),  # 두산 지주 본체
    # 이차전지 (화학·전기전자 업종에 분산)
    (["에코프로", "천보", "포스코퓨처", "엘앤에프", "L&F", "이차전지", "배터리", "솔루스", "씨아이에스", "나라엠앤디"], "BATTERY"),
    # 게임 (서비스업 내 분리)
    (["게임즈", "엔씨소프트", "크래프톤", "펄어비스", "위메이드", "컴투스", "넷마블", "카카오게임"], "GAME"),
    # 화장품/뷰티 (화학·서비스업 내 분리)
    (["코스맥스", "콜마", "클리오", "실리콘투", "화장품", "뷰티", "아모레", "LG생활건강"], "COSMETIC"),
    # 방산 (기계·전기전자 내 분리)
    (["한화에어로", "KAI", "한국항공우주", "LIG넥스원", "풍산", "방산", "에어로스페이스", "항공우주"], "DEFENSE"),
    # 조선 (운수장비 내 분리)
    (["조선", "한화오션", "현대중공업", "삼성중공업", "HD현대중공업", "STX조선"], "SHIPBUILDING"),
    # 플랫폼 (서비스업 내 분리)
    (["네이버", "카카오", "NAVER", "Kakao"], "PLATFORM"),
    # 반도체 소재·장비 (전기전자 내 세분화)
    (["솔브레인", "동진쎄미켐", "원익IPS", "주성엔지니어링", "리노공업", "파크시스템", "하나머티리얼즈", "SK실트론", "SEMCO", "반도체"], "SEMICONDUCTOR"),
    # 바이오 벤처 (의약품 외 분류 방지)
    (["바이오", "HLB", "알테오젠", "리가켐", "ABL바이오", "올릭스"], "BIOTECH"),
    # 헬스케어 (의료기기·서비스)
    (["임플란트", "덴티움", "오스템", "인바디", "뷰웍스", "바텍", "씨젠", "피씨엘"], "HEALTH"),
    # 대표 반도체 (전기전자 → SEMICONDUCTOR 보장)
    (["삼성전자", "SK하이닉스"], "SEMICONDUCTOR"),
]

# ── 2순위: KRX 업종 코드 → 섹터 (부분 문자열 매칭) ──────────────────────────
# 중요: 넓은 키워드보다 좁은 키워드를 먼저 배치 (첫 번째 매칭으로 결정됨)
INDUSTRY_MAP: list[tuple[str, str]] = [
    # ── 지주·기타금융 → ETC (금융 키워드보다 반드시 앞에 위치) ──
    ("지주",       "ETC"),
    ("holding",    "ETC"),
    ("기타금융",   "ETC"),
    # "투자" 앞에 "금융투자" 먼저 → 증권·자산운용사(금융투자업)는 FINANCE 유지
    ("금융투자",   "FINANCE"),
    # "투자" 단독 = 순수지주 (위에서 금융투자업은 이미 처리됨)
    ("투자",       "ETC"),

    # ── 반도체: 업종명에 직접 반도체가 명시된 경우만 ──
    # "전기전자"는 반도체와 무관한 전자기기·산업전기 기업도 포함하므로 제외
    # → 실제 반도체 기업은 THEME_HINTS에서 먼저 잡힘 (삼성전자·SK하이닉스 등)
    ("반도체",     "SEMICONDUCTOR"),

    # ── 바이오·제약 ──
    ("의약품",     "BIOTECH"),
    ("제약",       "BIOTECH"),
    ("바이오",     "BIOTECH"),
    ("의약물질",   "BIOTECH"),
    ("연구개발",   "BIOTECH"),

    # ── 화학 ──
    ("화학",       "CHEMICAL"),
    ("석유",       "CHEMICAL"),
    ("고무",       "CHEMICAL"),

    # ── 금융 (실제 금융서비스: 은행·보험·증권만 한정) ──
    ("은행",       "FINANCE"),
    ("보험",       "FINANCE"),
    ("증권",       "FINANCE"),
    ("카드",       "FINANCE"),
    ("캐피탈",     "FINANCE"),
    ("저축",       "FINANCE"),
    # "금융" 단독 = LG·SK·CJ·GS 등 그룹 지주사가 KIND에서 "금융"으로 분류됨
    # 실제 금융사(은행·보험·증권·금융투자)는 위에서 이미 처리되므로 여기 오면 지주사
    ("금융",       "ETC"),

    # ── 자동차·운수장비 ──
    ("운수장비",   "AUTO"),
    ("자동차",     "AUTO"),

    # ── 건설 ──
    ("건설",       "CONSTRUCTION"),
    ("시멘트",     "CONSTRUCTION"),
    ("부동산",     "CONSTRUCTION"),  # 리츠·부동산개발은 CONSTRUCTION에 가까움

    # ── 식품 ──
    ("음식료",     "FOOD"),
    ("식품",       "FOOD"),
    ("음료",       "FOOD"),
    ("담배",       "FOOD"),
    ("농업",       "FOOD"),

    # ── 통신 ──
    ("통신",       "TELECOM"),
    ("방송",       "TELECOM"),

    # ── 에너지 ──
    ("전기가스",   "ENERGY"),
    ("에너지",     "ENERGY"),
    ("전력",       "ENERGY"),
    ("가스",       "ENERGY"),
    ("전기업",     "ENERGY"),

    # ── 산업재·기계 (전기전자 포함: 두산 등 산업전기기계 기업 수용) ──
    ("기계",       "INDUSTRIAL"),
    ("전기전자",   "INDUSTRIAL"),   # 반도체와 무관한 산업전기·전자장비 기업
    ("전동기",     "INDUSTRIAL"),
    ("발전기",     "INDUSTRIAL"),
    ("절연선",     "INDUSTRIAL"),
    ("케이블",     "INDUSTRIAL"),

    # ── 철강·소재 ──
    ("철강",       "STEEL"),
    ("금속",       "STEEL"),
    ("광업",       "MATERIAL"),
    ("비금속",     "MATERIAL"),
    ("광물",       "MATERIAL"),
    ("종이",       "MATERIAL"),
    ("목재",       "MATERIAL"),
    ("유리",       "MATERIAL"),

    # ── 유통·리테일 ──
    ("유통",       "RETAIL"),
    ("도매",       "RETAIL"),
    ("소매",       "RETAIL"),
    ("백화점",     "RETAIL"),
    ("중개",       "RETAIL"),

    # ── 소비재 ──
    ("섬유",       "CONSUMER"),
    ("의류",       "CONSUMER"),
    ("소비재",     "CONSUMER"),
    ("오락",       "CONSUMER"),
    ("레저",       "CONSUMER"),
    ("봉제",       "CONSUMER"),
    ("가정용",     "CONSUMER"),
    ("출판",       "CONSUMER"),

    # ── 물류·운송 ──
    ("운수창고",   "LOGISTICS"),
    ("물류",       "LOGISTICS"),
    ("운송",       "LOGISTICS"),
    ("항공",       "LOGISTICS"),
    ("해운",       "LOGISTICS"),

    # ── 헬스케어 ──
    ("의료",       "HEALTH"),
    ("정밀",       "HEALTH"),

    # ── IT·소프트웨어 ──
    ("서비스",     "IT"),
    ("소프트웨어", "IT"),
    ("IT",         "IT"),
    ("정보",       "IT"),
    ("프로그래밍", "IT"),
    ("시스템",     "IT"),
    ("광고",       "IT"),
    ("전자부품",   "IT"),   # 전자부품은 반도체보다 IT 전자기기 쪽에 가까움

    # ── 이차전지 ──
    ("이차전지",   "BATTERY"),
    ("일차전지",   "BATTERY"),
]

DEFAULT_SECTOR = "ETC"


def _guess_sector(name: str, industry: str) -> str:
    # 1) 테마 키워드 우선
    for keywords, sector in THEME_HINTS:
        for kw in keywords:
            if kw in name:
                return sector
    # 2) KRX 업종 코드
    if industry:
        for keyword, sector in INDUSTRY_MAP:
            if keyword in industry:
                return sector
    return DEFAULT_SECTOR


def _fetch_naver_market(sosok: int, pages: int, headers: dict) -> list[dict]:
    """네이버 금융 시총순 페이지 스크래핑. sosok=0:KOSPI, 1:KOSDAQ"""
    import requests
    from bs4 import BeautifulSoup

    stocks = []
    for page in range(1, pages + 1):
        url = (
            f"https://finance.naver.com/sise/sise_market_sum.naver"
            f"?sosok={sosok}&page={page}"
        )
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        for tr in soup.select("table.type_2 tr"):
            tds = tr.select("td")
            if len(tds) < 7:
                continue
            a = tds[1].select_one("a")
            if not a:
                continue
            href = a.get("href", "")
            # href 예: /item/main.naver?code=005930
            code = href.split("code=")[-1] if "code=" in href else ""
            if not code:
                continue
            name = a.get_text(strip=True)
            marcap_txt = tds[6].get_text(strip=True).replace(",", "")
            try:
                marcap = int(marcap_txt) * 100_000_000  # 억 단위 → 원
            except ValueError:
                continue
            stocks.append({"Code": code.zfill(6), "Name": name, "Marcap": marcap})
        logger.debug("sosok=%d page=%d 누적=%d", sosok, page, len(stocks))
    return stocks


def fetch_top500() -> list[dict]:
    """네이버 금융 시총순 + KIND 업종으로 상위 500종목 구성."""
    import io
    import requests
    import pandas as pd

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com/sise/",
    }

    # ── 1) 네이버 금융: KOSPI + KOSDAQ 시총 상위 ────────────────────
    logger.info("네이버 금융 KOSPI 시총 스크래핑 중...")
    kospi_stocks  = _fetch_naver_market(0, pages=8, headers=headers)
    logger.info("네이버 금융 KOSDAQ 시총 스크래핑 중...")
    kosdaq_stocks = _fetch_naver_market(1, pages=8, headers=headers)

    all_stocks = kospi_stocks + kosdaq_stocks
    marcap_df = (
        pd.DataFrame(all_stocks)
        .drop_duplicates("Code")
        .sort_values("Marcap", ascending=False)
        .head(STOCK_LIMIT)
        .reset_index(drop=True)
    )
    logger.info("시총 상위 %d종목 수집 완료", len(marcap_df))

    # ── 2) KIND에서 업종 정보 조회 ───────────────────────────────────
    logger.info("KIND에서 업종 정보 조회 중...")
    try:
        kind_headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
        kind_base = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
        dfs = []
        for url in [kind_base, kind_base + "&marketType=kosdaqMkt"]:
            r_kind = requests.get(url, headers=kind_headers, timeout=20)
            r_kind.encoding = "euc-kr"
            df = pd.read_html(io.StringIO(r_kind.text), header=0)[0]
            dfs.append(df)
        kind_df = pd.concat(dfs, ignore_index=True)
        kind_df["Code"]     = kind_df["종목코드"].astype(str).str.zfill(6)
        kind_df["Industry"] = kind_df["업종"]
        kind_df = kind_df.drop_duplicates("Code")
        combined = pd.merge(marcap_df, kind_df[["Code", "Industry"]], on="Code", how="left")
        combined["Industry"] = combined["Industry"].fillna("")
        logger.info("업종 예시: %s", combined[["Name", "Industry"]].head(5).to_dict("records"))
    except Exception as e:
        logger.warning("KIND 업종 조회 실패 (%s) → 이름 키워드만 사용", e)
        combined = marcap_df.copy()
        combined["Industry"] = ""

    return combined.to_dict("records")


def seed_krx() -> None:
    client = get_client()

    # 1) 시총 상위 500 확보
    stocks_data = fetch_top500()

    # 2) 섹터 분류 통계 출력용
    sector_counts: dict[str, int] = {}

    # 3) Supabase upsert 용 rows 구성
    rows: list[dict] = []
    for item in stocks_data:
        ticker   = str(item["Code"]).zfill(6)
        name     = str(item["Name"])
        industry = str(item.get("Industry") or "")
        sector   = _guess_sector(name, industry)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        rows.append({
            "ticker":    ticker,
            "name":      name,
            "sector_id": sector,
            "aliases":   [],
        })

    # 섹터별 분포 로그
    for sec, cnt in sorted(sector_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-15s %3d종목", sec, cnt)

    # 4) Supabase upsert (배치 100)
    logger.info("Supabase upsert 중 (%d종목)...", len(rows))
    BATCH = 100
    for i in range(0, len(rows), BATCH):
        client.table("stocks").upsert(rows[i:i+BATCH], on_conflict="ticker").execute()

    logger.info("upsert 완료: %d종목", len(rows))

    # 5) 500위 밖으로 밀린 종목 정리 (raw_mentions 없는 것만 삭제)
    top_set = {r["ticker"] for r in rows}
    try:
        existing = client.table("stocks").select("ticker").execute()
        outside = [r["ticker"] for r in existing.data if r["ticker"] not in top_set]
        if outside:
            logger.info("500위 밖 종목 %d개 정리 시도...", len(outside))
            removed = 0
            for ticker in outside:
                ref = client.table("raw_mentions").select("id").eq("ticker", ticker).limit(1).execute()
                if ref.data:
                    logger.debug("%s: raw_mentions 참조 있음 → 유지", ticker)
                else:
                    client.table("stocks").delete().eq("ticker", ticker).execute()
                    removed += 1
            logger.info("정리 완료: %d개 삭제", removed)
    except Exception as e:
        logger.warning("500위 밖 종목 정리 실패 (무시): %s", e)

    print(f"\n완료: 시총 상위 {len(rows)}종목 적재.")
    print("섹터 분포:", {k: v for k, v in sorted(sector_counts.items(), key=lambda x: -x[1])})


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import dotenv, pathlib
    dotenv.load_dotenv(pathlib.Path(__file__).parents[3] / ".env")

    seed_krx()
