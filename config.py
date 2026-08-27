import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# Nạp file .env nếu có
load_dotenv(dotenv_path=BASE_DIR / ".env")

AUTH_FILE = BASE_DIR / "auth.json"

# URL dịch vụ - hỗ trợ override qua biến môi trường cho staging/testing
LIS_HOME_URL = os.getenv("LIS_HOME_URL", "https://lis.larion.com/")
IMPORTER_URL = os.getenv("IMPORTER_URL", "https://importer.larion.com/")

LIS_USERNAME = os.getenv("LIS_USERNAME", "")
LIS_PASSWORD = os.getenv("LIS_PASSWORD", "")

# Tự động bật HEADLESS nếu chạy trên CI / Jenkins
is_ci = bool(os.getenv("CI") or os.getenv("JENKINS_URL") or os.getenv("JENKINS_HOME"))
HEADLESS = os.getenv("HEADLESS", "True" if is_ci else "False").lower() in ("true", "1", "t", "yes")
