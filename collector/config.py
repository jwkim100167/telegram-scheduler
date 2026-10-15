import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]

DART_API_KEY: str = os.environ["DART_API_KEY"]

# 에이징 기준 주 수 (기본 13주 = 약 1분기)
AGING_WEEKS: int = int(os.environ.get("AGING_WEEKS", "13"))
