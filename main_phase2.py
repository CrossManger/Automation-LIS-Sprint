import os
import sys
import time
from playwright.sync_api import sync_playwright

import config
from login import login_and_save_session
from data_loader import load_milestone_from_file
from lis_service import filter_and_assign_sprint_milestone


def run_phase2_pipeline(data_file: str | None = None) -> bool:
    """
    Điểm vào thực thi toàn diện cho Giai đoạn 2 (Phase 2):
      - Đăng nhập và xác thực phiên LIS.
      - Lọc danh sách công việc theo ngày Start date, Due date, dự án MAX.
      - Gán hàng loạt Target Milestone và Sprint bằng Context Menu.
    """
    print("=" * 70)
    print("🚀 KHỞI ĐỘNG TIẾN TRÌNH TỰ ĐỘNG HÓA GIAI ĐOẠN 2 (PHASE 2)")
    print("=" * 70)

    # 1. Đăng nhập và chuẩn bị phiên nếu chưa có auth.json
    if not os.path.exists("auth.json"):
        print("[*] Không tìm thấy phiên đăng nhập 'auth.json'. Đang tiến hành đăng nhập...")
        login_success = login_and_save_session()
        if not login_success:
            print("[X] LỖI: Đăng nhập LIS thất bại. Dừng tiến trình Giai đoạn 2.")
            return False

    # 2. Nạp dữ liệu cấu hình từ file hoặc biến môi trường Jenkins
    milestone_data = {}
    target_file = data_file or os.getenv("DATA_FILE", "test.json")
    try:
        milestone_data = load_milestone_from_file(target_file)
        print(f"[*] Đã nạp thành công thông tin cấu hình từ: '{target_file}'")
    except Exception as e:
        print(f"[!] Cảnh báo nạp file '{target_file}': {e}. Sẽ dùng biến môi trường hoặc tham số CLI.")

    cli_proj = sys.argv[1] if len(sys.argv) > 1 else None
    proj_id = (
        cli_proj
        or os.getenv("PROJECT_ID")
        or milestone_data.get("Project ID Importer")
        or "786"
    )
    sprint_name = (
        os.getenv("SPRINT_NAME")
        or os.getenv("NAME_SPRINT")
        or milestone_data.get("Name Sprint", "2026 Oct 01 Sprint")
    )
    start_date = (
        os.getenv("START_DATE")
        or os.getenv("RELEASE_START_DATE")
        or milestone_data.get("Release Start Date", "2026-10-01")
    )
    due_date = (
        os.getenv("DUE_DATE")
        or os.getenv("RELEASE_SUBMISSION_DATE")
        or milestone_data.get("Release Submission Date", "2026-10-17")
    )

    print(f"[*] THÔNG SỐ GIAI ĐOẠN 2:")
    print(f"  - Project ID:    {proj_id}")
    print(f"  - Sprint Name:   {sprint_name}")
    print(f"  - Start Date:    {start_date}")
    print(f"  - Due Date:      {due_date}")
    print(f"  - Headless Mode: {config.HEADLESS}")

    # 3. Khởi tạo trình duyệt Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.HEADLESS,
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            storage_state="auth.json",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        # 4. Thực thi quy trình lọc và gán Sprint / Milestone
        success = filter_and_assign_sprint_milestone(
            page=page,
            proj_id=str(proj_id),
            sprint_name=sprint_name,
            start_date=start_date,
            due_date=due_date,
            proj_name_keyword="MAX",
            exclude_proj_name="EGG"
        )

        if not config.HEADLESS and sys.stdin and sys.stdin.isatty():
            try:
                input("\n👉 Nhấn ENTER để đóng trình duyệt...")
            except Exception:
                pass

        browser.close()
        return success


if __name__ == "__main__":
    success = run_phase2_pipeline()
    sys.exit(0 if success else 1)
