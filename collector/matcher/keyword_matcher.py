"""
종목명 / 종목코드 / 별칭을 텍스트에서 매칭한다.
LLM 호출 없이 사전(dict) 기반으로만 동작한다.

사용 예:
    matcher = KeywordMatcher()
    matcher.load_from_supabase()
    tickers = matcher.match("삼성전자와 SK하이닉스가 반도체 수출을 ...")
    # -> {"005930", "000660"}
"""

from collector.db.supabase_client import fetch_stocks


class KeywordMatcher:
    def __init__(self) -> None:
        # keyword -> ticker 역방향 사전
        # 긴 키워드를 먼저 매칭하기 위해 로드 후 정렬
        self._map: dict[str, str] = {}

    def load_from_supabase(self) -> None:
        """stocks 테이블에서 종목 목록을 불러와 사전을 구성한다."""
        stocks = fetch_stocks()
        mapping: dict[str, str] = {}
        for stock in stocks:
            ticker: str = stock["ticker"]
            # 종목코드 자체도 키워드로 등록
            mapping[ticker] = ticker
            # 종목명
            mapping[stock["name"]] = ticker
            # 별칭 배열 (Supabase에서 list로 옴)
            for alias in stock.get("aliases") or []:
                if alias:
                    mapping[alias] = ticker
        # 긴 키워드를 먼저 매칭해 부분 매칭 오류 방지
        self._map = dict(sorted(mapping.items(), key=lambda x: -len(x[0])))

    def match(self, text: str) -> set[str]:
        """
        텍스트에서 히트된 ticker 집합을 반환한다.
        같은 글에 동일 종목이 N번 나와도 set 이므로 1회로 카운트된다.
        """
        found: set[str] = set()
        for keyword, ticker in self._map.items():
            if keyword in text:
                found.add(ticker)
        return found
