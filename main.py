import os
import re
import sys
from playwright.sync_api import sync_playwright

import config
from login import login_and_save_session
from data_loader import load_milestone_from_file
from utils import (
    safe_goto,
    safe_input,
    check_form_error,
    select_option_with_fallback,
    get_sprint_name,
)
from lis_service import (
    verify_project_access,
    set_project_settings,
    fill_milestone_form,
    fill_sprint_form,
    select_assignee_smartly,
    fill_task_form,
    extract_task_id,
    extract_work_items_task_id,
)
from importer_service import (
    find_completed_import_in_table,
    fill_importer_form,
    ImportSummaryTracker,
    execute_import_with_retry,
)

# Re-exports để đảm bảo tính tương thích ngược hoàn toàn 100%
__all__ = [
    "safe_goto",
    "safe_input",
    "check_form_error",
    "select_option_with_fallback",
    "get_sprint_name",
    "verify_project_access",
    "set_project_settings",
    "fill_milestone_form",
    "fill_sprint_form",
    "select_assignee_smartly",
    "fill_task_form",
    "extract_task_id",
    "extract_work_items_task_id",
    "find_completed_import_in_table",
    "fill_importer_form",
    "ImportSummaryTracker",
    "execute_import_with_retry",
    "run_automation",
]


def run_automation(data_file_path: str | None = None):
    """
    Hàm điều phối kịch bản tự động hóa toàn diện từ Thao tác 1 đến Thao tác 18:
      - Quản lý phiên đăng nhập và trình duyệt Playwright
      - Tạo Milestone, Sprint, Task trên LIS
      - Quản lý cài đặt cấu hình Planned / Public của dự án
      - Import 2 tầng Subtasks trên Importer với cơ chế tự động thử lại (retry)
      - Trích xuất Task ID và khôi phục cài đặt dự án
      - Báo cáo tổng kết tình trạng import
    """
    # 1. Nạp dữ liệu từ file cấu hình hoặc biến môi trường Jenkins
    try:
        milestone = load_milestone_from_file(data_file_path)
        sprint_name = get_sprint_name(milestone)
        print(f"[✓] Đã nạp thành công dữ liệu Sprint: '{sprint_name}'")
    except Exception as e:
        print(f"[X] LỖI NẠP THÔNG TIN SPRINT: {e}")
        sys.exit(1)

    # Khởi tạo trình theo dõi tình trạng 2 lần import
    import_tracker = ImportSummaryTracker()

    # 2. Kiểm tra nếu chưa có file phiên đăng nhập thì đăng nhập trước
    if not config.AUTH_FILE.exists():
        print("[*] Chưa có file phiên đăng nhập (auth.json). Đang tiến hành đăng nhập lần đầu...")
        if not login_and_save_session():
            print("[X] Đăng nhập thất bại. Dừng chương trình.")
            sys.exit(1)

    print("[*] Khởi động trình duyệt với phiên đăng nhập đã lưu...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        context = browser.new_context(
            storage_state=str(config.AUTH_FILE),
            viewport={"width": 1920, "height": 1080}
        )

        page = context.new_page()
        print(f"[*] Đang truy cập trang chủ LIS: {config.LIS_HOME_URL}")
        safe_goto(page, config.LIS_HOME_URL)
        page.wait_for_load_state("networkidle")

        # Kiểm tra xem có bị chuyển về trang login (phiên hết hạn) không
        if "login" in page.url:
            print("[!] Phiên đăng nhập đã hết hạn. Đang xóa auth.json và đăng nhập lại...")
            if config.AUTH_FILE.exists():
                os.remove(config.AUTH_FILE)
            browser.close()
            if not login_and_save_session():
                print("[X] Đăng nhập lại thất bại. Dừng chương trình.")
                sys.exit(1)
            return run_automation(data_file_path)

        print(f"[✓] Đã vào trang chủ: {page.title()} ({page.url})")

        # ==========================================
        # Thao tác 1: Điều hướng trực tiếp đến trang Dự án qua Project ID
        # ==========================================
        proj_id = str(milestone.get("Project ID Importer") or os.getenv("PROJECT_ID") or "786").strip()
        project_url = f"{config.LIS_HOME_URL.rstrip('/')}/projects/{proj_id}"
        print(f"[*] Đang điều hướng trực tiếp đến trang dự án (Project ID: {proj_id}): {project_url}")
        res = safe_goto(page, project_url)
        page.wait_for_load_state("networkidle")

        # Kiểm tra tính hợp lệ của trang dự án (phát hiện sớm khi nhập sai Project ID -> 403 / 404)
        is_accessible, access_error = verify_project_access(page, proj_id, response=res)
        if not is_accessible:
            print(f"\n[X] LỖI TRUY CẬP DỰ ÁN: {access_error}")
            print(f"    - Tiêu đề trang: {page.title()}")
            print(f"    - URL hiện tại:  {page.url}")
            print(f"\n  👉 NGUYÊN NHÂN & CÁCH KHẮC PHỤC:")
            print(f"     1. Bạn đang cấu hình Project ID: '{proj_id}'. Vui lòng kiểm tra lại xem có nhập nhầm mã dự án không (ví dụ: Team MAX là 786).")
            print(f"     2. Dự án #{proj_id} có thể không tồn tại hoặc đã bị đóng/lưu trữ (Archived) trên LIS.")
            print(f"     3. Tài khoản '{milestone.get('Author Importer') or config.LIS_USERNAME}' chưa được thêm quyền thành viên trong dự án này.")
            browser.close()
            sys.exit(1)

        print(f"[✓] Đã vào trang dự án: {page.title()} ({page.url})")

        # Ghi nhớ đường dẫn Settings của dự án để dùng xuyên suốt
        project_settings_url = f"{config.LIS_HOME_URL.rstrip('/')}/projects/{proj_id}/settings"
        print(f"[✓] Đã ghi nhớ đường dẫn Settings của dự án: {project_settings_url}")

        # ==========================================
        # Thao tác 3: Vào Roadmap
        # ==========================================
        print("[*] Đang vào mục 'Roadmap'...")
        roadmap_link = page.locator("a, button, li").filter(has_text=re.compile(r"^Roadmap$", re.IGNORECASE)).first
        if roadmap_link.count() == 0:
            roadmap_link = page.locator("a:has-text('Roadmap'), .roadmap, a[href*='roadmap']").first

        try:
            roadmap_link.wait_for(state="visible", timeout=10000)
            roadmap_link.click()
            page.wait_for_load_state("networkidle")
            print(f"[✓] Đã vào trang Roadmap: {page.title()}")
        except Exception:
            print(f"\n[X] LỖI: Không tìm thấy hoặc không thể mở mục 'Roadmap' trong dự án #{proj_id}.")
            print(f"    - Tiêu đề trang hiện tại: {page.title()} ({page.url})")
            print(f"  👉 Nguyên nhân có thể do:")
            print(f"     1. Dự án #{proj_id} chưa bật module 'Roadmap' trong mục Settings -> Modules.")
            print(f"     2. Tài khoản không có quyền xem Roadmap trong dự án này.")
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 4: Bấm 'New milestone'
        # ==========================================
        print("[*] Đang nhấp vào 'New milestone'...")
        new_milestone_btn = page.locator("a, button").filter(has_text=re.compile(r"New\s+milestone", re.IGNORECASE)).first
        if new_milestone_btn.count() == 0:
            new_milestone_btn = page.locator("a[href*='versions/new'], a[href*='milestone']").first

        try:
            new_milestone_btn.wait_for(state="visible", timeout=10000)
            new_milestone_btn.click()
            page.wait_for_load_state("networkidle")
        except Exception:
            print(f"\n[X] LỖI: Không tìm thấy nút 'New milestone' trên trang Roadmap (Dự án #{proj_id}).")
            print(f"  👉 Nguyên nhân: Tài khoản có thể không có quyền quản lý/tạo Milestone (Versions) trên dự án này.")
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 5: Điền form tạo milestone
        # ==========================================
        if not fill_milestone_form(page, milestone):
            print("\n[X] DỪNG QUY TRÌNH: Tạo Milestone thất bại.")
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 6: Nhấp vào mục "Agile board"
        # ==========================================
        print("\n[*] Đang vào mục 'Agile board'...")
        page.locator("#main-menu a[href*='agile'], #main-menu a:has-text('Agile'), a[href*='easy_agile_boards']").first.click()
        page.wait_for_load_state("domcontentloaded")
        print(f"[✓] Đã chuyển tới trang Agile board: {page.title()} ({page.url})")

        # ==========================================
        # Thao tác 7: Nhấp vào nút "New sprint" trên giao diện
        # ==========================================
        print("[*] Đang tìm và nhấp vào nút 'New sprint'...")
        new_sprint_selector = "a[title='New sprint'], .primary-actions a:has-text('New sprint'), a[href*='easy_sprints/new'], a:has-text('New sprint')"

        try:
            page.wait_for_selector(new_sprint_selector, state="attached", timeout=10000)
            new_sprint_btn = page.locator(new_sprint_selector).first
            new_sprint_btn.dispatch_event("click")
            page.wait_for_load_state("networkidle")
            print(f"[✓] Đã nhấp vào 'New sprint' thành công! URL: {page.url}")
        except Exception:
            print("\n[X] LỖI: Không tìm thấy hoặc không thể nhấp vào nút 'New sprint' trên giao diện Agile board.")
            print("  👉 Nguyên nhân có thể do:")
            print("     1. Tài khoản không có quyền tạo Sprint trong dự án này.")
            print("     2. Dự án này chưa bật tính năng Agile / Scrum board.")
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 8: Điền form và tạo Sprint
        # ==========================================
        if not fill_sprint_form(page, milestone):
            print("\n[X] DỪNG QUY TRÌNH: Tạo Sprint thất bại.")
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 9: Settings - Planned = BẬT, Public = TẮT
        # ==========================================
        set_project_settings(page, planned=True, public=False, settings_url=project_settings_url)

        # ==========================================
        # Thao tác 10: Nhấp vào "New task" trên menu top dự án
        # ==========================================
        print("\n[*] Đang tìm và nhấp vào 'New task'...")
        new_task_btn = page.locator("#main_menu_top_project a.issue-new, #main_menu_top_project a[href*='issues/new'], #main_menu_top_project a:has-text('New task')").first

        new_task_btn.scroll_into_view_if_needed()
        try:
            new_task_btn.click(timeout=5000)
        except Exception:
            new_task_btn.click(force=True, timeout=5000)

        page.wait_for_load_state("networkidle")
        print(f"[✓] Đã vào đúng trang tạo Task thành công! URL: {page.url}")

        # ==========================================
        # Thao tác 11: Điền thông tin và tạo Task mới
        # ==========================================
        is_task_success, task_id = fill_task_form(page, milestone)

        if not is_task_success or not task_id:
            print("\n[X] DỪNG QUY TRÌNH: Không tạo được Parent Task.")
            set_project_settings(page, planned=False, public=True, settings_url=project_settings_url)
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 12: Mở thêm Tab mới cho trang Importer
        # ==========================================
        print(f"\n[*] Đang mở thêm Tab mới cho trang Importer: {config.IMPORTER_URL}...")
        importer_page = context.new_page()
        safe_goto(importer_page, config.IMPORTER_URL)
        importer_page.wait_for_load_state("networkidle")
        print(f"[✓] Đã mở thành công Tab 2 (Importer): {importer_page.title()} ({importer_page.url})")

        # ==========================================
        # Thao tác 13: Import Lần 1 - Nạp Cấu Trúc (Structure Template -> Parent Task)
        # ==========================================
        print("\n=== BẮT ĐẦU IMPORT LẦN 1: TẠO CẤU TRÚC SUBTASKS MẪU ===")
        l1_success, l1_attempts, l1_status = execute_import_with_retry(
            importer_page, milestone, task_id, file_key="Upload File",
            layer_name="Import Tầng 1 (Cấu trúc Sprint)", lis_page=page, max_retries=0
        )
        import_tracker.update("layer1", success=l1_success, status=l1_status)

        if not l1_success:
            print(f"\n[X] DỪNG QUY TRÌNH: Import Tầng 1 (Structure Template) thất bại ({l1_status}).")
            import_tracker.update("layer2", success=False, status="Không thực hiện (do Tầng 1 thất bại)")
            import_tracker.print_summary()
            set_project_settings(page, planned=False, public=True, settings_url=project_settings_url)
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 14: Chuyển tiêu điểm (Focus) trở lại Tab 1 (LIS)
        # ==========================================
        print("\n[*] Đang chuyển tiêu điểm màn hình trở lại Tab 1 (LIS)...")
        page.bring_to_front()
        try:
            page.reload()
            page.wait_for_load_state("networkidle")
        except Exception:
            pass
        print(f"[✓] Đã quay trở lại màn hình Tab 1 (LIS - Task #{task_id}) thành công!")

        # ==========================================
        # Thao tác 15: Trích xuất và lưu Task ID của 'WORK ITEMS'
        # ==========================================
        print("\n[*] Đang tìm và trích xuất Task ID của task con 'WORK ITEMS'...")
        work_items_task_id = extract_work_items_task_id(page)

        if not work_items_task_id:
            print("\n[X] LỖI NGHIÊM TRỌNG: Không tìm thấy task con 'WORK ITEMS' trên LIS sau khi Import Tầng 1!")
            print("    -> Vui lòng kiểm tra lại file Structure Template hoặc kiểm tra trực tiếp trên LIS.")
            import_tracker.update("layer2", success=False, status="Không thể thực hiện (không tìm thấy task WORK ITEMS)")
            import_tracker.print_summary()
            set_project_settings(page, planned=False, public=True, settings_url=project_settings_url)
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 16: Import Lần 2 - Nạp Chi Tiết WORK ITEMS (vào work_items_task_id)
        # ==========================================
        print("\n=== BẮT ĐẦU IMPORT LẦN 2: NẠP CHI TIẾT WORK ITEMS ===")
        print(f"[*] Đang chuyển tiêu điểm sang Tab 2 (Importer) để nạp dữ liệu cho Task #{work_items_task_id}...")
        importer_page.bring_to_front()

        # Tải lại trang Importer để làm mới form sạch sẽ
        safe_goto(importer_page, config.IMPORTER_URL)
        importer_page.wait_for_load_state("networkidle")

        l2_success, l2_attempts, l2_status = execute_import_with_retry(
            importer_page, milestone, work_items_task_id, file_key="Upload Work Items File",
            layer_name="Import Tầng 2 (Chi tiết Work Items)", lis_page=page, max_retries=0
        )
        import_tracker.update("layer2", success=l2_success, status=l2_status)

        if not l2_success:
            print(f"\n[X] DỪNG QUY TRÌNH: Import Tầng 2 (Work Items Detail) thất bại ({l2_status}).")
            import_tracker.print_summary()
            set_project_settings(page, planned=False, public=True, settings_url=project_settings_url)
            browser.close()
            sys.exit(1)

        # ==========================================
        # Thao tác 17: Chuyển tiêu điểm trở lại Tab 1 (LIS) để kiểm tra kết quả cuối cùng
        # ==========================================
        print("\n[*] Đang chuyển tiêu điểm trở lại Tab 1 (LIS)...")
        page.bring_to_front()
        try:
            page.reload()
            page.wait_for_load_state("networkidle")
        except Exception:
            pass
        print("[✓] Đã tải lại và hiển thị toàn bộ cây Task hoàn chỉnh trên LIS!")

        # ==========================================
        # Thao tác 18: Khôi phục cài đặt Settings (Public = BẬT, Planned = TẮT)
        # ==========================================
        set_project_settings(page, planned=False, public=True, settings_url=project_settings_url)

        # ==========================================
        # Hoàn tất & Báo cáo tổng kết
        # ==========================================
        print(f"\n[✓] HOÀN THÀNH TOÀN BỘ QUY TRÌNH TỰ ĐỘNG HÓA THÀNH CÔNG RỰC RỠ!")
        print(f"    - Parent Task ID:     #{task_id}")
        print(f"    - WORK ITEMS Task ID: #{work_items_task_id}")
        print(f"    - Cài đặt dự án:      Public = Checked | Planned = Unchecked")

        # In báo cáo tổng kết trạng thái của cả 2 lần Import
        import_tracker.print_summary()

        # Chỉ tạm dừng chờ phím nếu chạy trực tiếp bằng dòng lệnh CLI trong terminal
        if not config.HEADLESS and not os.getenv("WEB_MODE") and sys.stdin and sys.stdin.isatty():
            try:
                input("\n👉 [INFO] Trình duyệt đang được giữ nguyên trên màn hình. Nhấn phím ENTER để đóng trình duyệt...")
            except Exception:
                pass

        browser.close()
        print("[✓] Đã đóng trình duyệt.")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        run_automation(input_file)
    except Exception as e:
        print(f"\n[X] LỖI THỰC THI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
