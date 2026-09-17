import os
import re
import time
import shutil
from pathlib import Path
from playwright.sync_api import Page
import config
from utils import safe_goto


def find_completed_import_in_table(
    importer_page: Page,
    target_filename: str,
    task_id: str | None = None,
    initial_item_ids: set | None = None
) -> dict | None:
    """
    Kiểm tra bảng lịch sử import trên Importer (bảng <tbody> với ng-repeat="item in items").
    Mỗi hàng có cấu trúc:
      td[0]: Item ID (ví dụ: 1332)
      td[1]: Link file và tên file (ví dụ: test2.xlsx)
      td[2]: Trạng thái (ví dụ: Complete)
      td[3]: Link download log CSV (ví dụ: /log/out_786_490604_minhvh.csv)
      td[4]: Nút Re-import
    Trả về thông tin bản ghi nếu trạng thái là Complete hoặc thông báo lỗi nếu Failed.
    """
    try:
        rows = importer_page.locator("tr[ng-repeat*='item in items']")
        if rows.count() == 0:
            rows = importer_page.locator("table tbody tr")

        row_count = rows.count()
        target_name_clean = target_filename.strip().lower()

        for i in range(row_count):
            row = rows.nth(i)
            cells = row.locator("td")
            if cells.count() < 3:
                continue

            item_id = cells.nth(0).inner_text().strip()
            # Bỏ qua các bản ghi cũ đã có từ trước lần submit này
            if initial_item_ids is not None and item_id in initial_item_ids:
                continue

            file_text = cells.nth(1).inner_text().strip()
            status_text = cells.nth(2).inner_text().strip()

            log_link = ""
            if cells.count() >= 4:
                log_a = cells.nth(3).locator("a")
                if log_a.count() > 0:
                    log_link = log_a.first.get_attribute("href") or ""

            # Kiểm tra xem có khớp tên file hoặc khớp Task ID trong link log không
            file_clean = file_text.lower()
            file_matched = (target_name_clean in file_clean) or (file_clean in target_name_clean)
            task_matched = bool(task_id and f"_{task_id}_" in log_link)

            # Nếu tên file hoặc Task ID khớp
            if file_matched or task_matched:
                if "complete" in status_text.lower():
                    return {
                        "item_id": item_id,
                        "filename": file_text,
                        "status": status_text,
                        "log_link": log_link,
                        "is_success": True
                    }
                elif any(err in status_text.lower() for err in ["fail", "error"]):
                    return {
                        "item_id": item_id,
                        "filename": file_text,
                        "status": status_text,
                        "log_link": log_link,
                        "is_success": False
                    }
    except Exception:
        pass

    return None


def fill_importer_form(importer_page: Page, item: dict, task_id: str, file_key: str, lis_page: Page | None = None) -> tuple[bool, str]:
    """
    Điền các thông tin vào form trên trang Importer (https://importer.larion.com/):
      1. Project ID                    -> #inputProject (từ 'Project ID Importer')
      2. Parent Task/Issue ID          -> input[name='issueId'] (từ biến task_id)
      3. Author                        -> input[name='author'] (từ 'Author Importer')
      4. File Type                     -> Radio 'Google Doc' (bỏ chọn 'MS-Project')
      5. Upload file                   -> File cấu hình bắt buộc từ JSON (theo file_key)
      6. Checkbox Project Status       -> input[ng-model='project_planing']
    Trả về: (is_success, stopped_percent) ví dụ (True, "100%") hoặc (False, "45%")
    """
    print(f"\n[*] Đang tiến hành điền form trên trang Importer (Target Task ID: #{task_id})...")

    # Kiểm tra file upload trước khi điền form để tránh mất thời gian nếu thiếu file
    upload_filename = item.get(file_key)
    if not upload_filename:
        print(f"\n[X] LỖI CẤU HÌNH: Không tìm thấy trường '{file_key}' trong file JSON dữ liệu!")
        return False, "0% (thiếu cấu hình file)"

    p_up = Path(upload_filename)
    if p_up.exists() and p_up.is_file():
        upload_file_path = p_up
    elif (config.BASE_DIR / upload_filename).exists() and (config.BASE_DIR / upload_filename).is_file():
        upload_file_path = config.BASE_DIR / upload_filename
    elif (config.BASE_DIR / p_up.name).exists() and (config.BASE_DIR / p_up.name).is_file():
        upload_file_path = config.BASE_DIR / p_up.name
    elif hasattr(config, "PROJECT_ROOT") and (config.PROJECT_ROOT / upload_filename).exists():
        upload_file_path = config.PROJECT_ROOT / upload_filename
    elif hasattr(config, "PROJECT_ROOT") and (config.PROJECT_ROOT / p_up.name).exists():
        upload_file_path = config.PROJECT_ROOT / p_up.name
    else:
        print(f"\n[X] LỖI: Không tìm thấy file upload '{upload_filename}' tại đường dẫn: {config.BASE_DIR / p_up.name}")
        return False, "0% (không tìm thấy file)"

    # Đảm bảo file upload luôn có phần mở rộng .xlsx hoặc .xls hợp lệ để Importer không bị nghẽn
    if upload_file_path.suffix.lower() not in [".xlsx", ".xls"]:
        valid_excel_path = upload_file_path.parent / f"{upload_file_path.stem}.xlsx"
        try:
            shutil.copy2(upload_file_path, valid_excel_path)
            upload_file_path = valid_excel_path
            print(f"  [*] Đã chuyển đổi tên file tạm sang chuẩn Excel: '{upload_file_path.name}'")
        except Exception:
            pass

    last_percent = "0%"
    try:
        # 1. Project ID Importer
        proj_id_importer = item.get("Project ID Importer", "786")
        project_input = importer_page.locator("#inputProject, input[name='project']").first
        project_input.wait_for(state="visible", timeout=15000)
        project_input.fill(str(proj_id_importer))
        project_input.dispatch_event("input")
        project_input.dispatch_event("change")
        project_input.press("Tab")
        print(f"  -> [✓] Đã điền Project ID: '{proj_id_importer}'")

        # Đợi AngularJS validate và mở khóa (enable) các ô tiếp theo
        try:
            importer_page.wait_for_function(
                "() => { const el = document.querySelector('input[name=\"issueId\"], input[name=\"author\"]'); return el && !el.disabled; }",
                timeout=10000
            )
        except Exception:
            importer_page.wait_for_timeout(1000)

        # 2. Parent Task / Issue ID (Biến task_id đã lưu)
        if task_id:
            issue_input = importer_page.locator("input[name='issueId'], input[placeholder*='Parent Task']").first
            issue_input.wait_for(state="visible", timeout=10000)
            issue_input.fill(str(task_id))
            issue_input.dispatch_event("input")
            issue_input.dispatch_event("change")
            issue_input.press("Tab")
            print(f"  -> [✓] Đã điền Parent Task ID: '{task_id}'")

        # 3. Author Importer (Tự động dùng LIS Username)
        author_importer = item.get("Author Importer") or config.LIS_USERNAME or os.getenv("LIS_USERNAME", "")
        if author_importer:
            author_input = importer_page.locator("input[name='author'], input[placeholder*='Redmine Login']").first
            author_input.wait_for(state="visible", timeout=10000)
            author_input.fill(str(author_importer))
            author_input.dispatch_event("input")
            author_input.dispatch_event("change")
            author_input.press("Tab")
            print(f"  -> [✓] Đã điền Author (từ LIS Username): '{author_importer}'")

        # 4. Chọn Radio 'Google Doc' (bỏ chọn MS-Project)
        google_doc_radio = importer_page.locator("input[type='radio'][value='google-doc']").first
        google_doc_radio.wait_for(state="attached", timeout=10000)
        google_doc_radio.check()
        print("  -> [✓] Đã tick chọn 'Google Doc' (và không chọn 'MS-Project')")

        # 5. Upload file từ đường dẫn đã kiểm tra ở trên
        file_input = importer_page.locator("#inputFile, input[type='file'][name='file'], input[type='file']").first
        file_input.set_input_files(str(upload_file_path))
        file_desc = "File Cấu trúc Sprint (Structure Template)" if file_key == "Upload File" else "File Chi tiết Work Items"
        print(f"  -> [✓] Đã đính kèm thành công {file_desc} vào form Importer")

        # 6. Tích chọn ô Checkbox "I already set Project Status to 'planing'"
        planning_checkbox = importer_page.locator("input[ng-model='project_planing'], input[type='checkbox']").first
        planning_checkbox.wait_for(state="visible", timeout=10000)
        planning_checkbox.set_checked(True)
        print("  -> [✓] Đã tick chọn ô 'I already set Project Status to planing'")

        # 7. Bấm nút Submit và chờ thanh Progress Bar hoặc bảng kết quả đạt Complete
        print("  [*] Đang bấm nút 'Submit' trên Importer...")
        submit_btn = importer_page.locator("button.btn-primary, button[type='submit']").filter(has_text="Submit").first

        # Ghi nhận các ID bản ghi hiện có trong bảng Importer trước khi gửi
        initial_item_ids = set()
        try:
            existing_rows = importer_page.locator("tr[ng-repeat*='item in items'], table tbody tr")
            for idx in range(existing_rows.count()):
                first_td = existing_rows.nth(idx).locator("td").first
                if first_td.count() > 0:
                    tid = first_td.inner_text().strip()
                    if tid:
                        initial_item_ids.add(tid)
            if initial_item_ids:
                print(f"  [*] Đã ghi nhận {len(initial_item_ids)} bản ghi cũ trong bảng Importer trước khi gửi.")
        except Exception:
            pass

        # Đợi nút Submit được mở khóa (enabled)
        try:
            importer_page.wait_for_function(
                "() => { const btn = document.querySelector('button.btn-primary, button[type=\"submit\"]'); return btn && !btn.disabled; }",
                timeout=15000
            )
        except Exception:
            pass

        submit_btn.click()
        print("  [*] Đã bấm Submit. Đang theo dõi tiến trình upload (chờ thanh tiến trình đạt 100% hoặc bảng xuất hiện trạng thái Complete)...")

        # Theo dõi tiến trình theo thời gian thực cho đến khi hoàn tất (tối đa 5 phút)
        start_time = time.time()
        is_completed = False
        started_uploading = False
        completed_record = None

        while time.time() - start_time < 300:
            # ƯU TIÊN 1: Kiểm tra bảng kết quả Importer (tbody tr với ng-repeat="item in items")
            completed_record = find_completed_import_in_table(
                importer_page,
                target_filename=upload_file_path.name,
                task_id=str(task_id) if task_id else None,
                initial_item_ids=initial_item_ids
            )
            if completed_record:
                if completed_record["is_success"]:
                    print(f"\n  -> [✓] XÁC NHẬN THÀNH CÔNG TỪ BẢNG KẾT QUẢ IMPORTER (Item #{completed_record['item_id']}):")
                    print(f"       * Tên file:   {completed_record['filename']}")
                    print(f"       * Trạng thái: {completed_record['status']}")
                    is_completed = True
                    break
                else:
                    print(f"\n  -> [X] BẢNG IMPORTER BÁO LỖI (Item #{completed_record['item_id']}): Trạng thái '{completed_record['status']}'")
                    if completed_record.get("log_link"):
                        full_log_url = f"{config.IMPORTER_URL.rstrip('/')}/{completed_record['log_link'].lstrip('/')}"
                        print(f"       * File log lỗi: {full_log_url}")
                    return False, last_percent

            # ƯU TIÊN 2: Theo dõi thanh progress bar
            try:
                progress_bar = importer_page.locator(".progress .progress-bar")
                progress_container = importer_page.locator(".progress")

                if progress_bar.count() > 0:
                    text = progress_bar.first.inner_text().strip()
                    aria_val = progress_bar.first.get_attribute("aria-valuenow")
                    is_visible = progress_container.first.is_visible() if progress_container.count() > 0 else False

                    # In phần trăm tiến độ khi có số thay đổi (e.g. 20%, 25%, ...)
                    match_num = re.search(r"\d+%", text)
                    current_percent = match_num.group(0) if match_num else (f"{aria_val}%" if aria_val and aria_val.isdigit() else None)
                    if current_percent and current_percent != last_percent:
                        last_percent = current_percent
                        started_uploading = True
                        print(f"  -> Tiến độ import: {last_percent}")

                    # Điều kiện 1: Đạt đúng 100%
                    if "100%" in text or aria_val == "100":
                        print("  -> [✓] Thanh tiến trình đã đạt 100% hoàn tất!")
                        is_completed = True
                        break

                    # Điều kiện 2: Sau khi đã chạy tiến độ, server xử lý xong và AngularJS ẩn/reset thanh tiến trình về '%' hoặc rỗng
                    if started_uploading and (text in ("", "%") or not is_visible):
                        print("  -> [✓] Quá trình xử lý upload dữ liệu trên Importer đã hoàn tất (thanh tiến trình đã tự động đóng)!")
                        is_completed = True
                        break
                else:
                    # Điều kiện 2b: Thanh tiến trình bị gỡ bỏ hoàn toàn khỏi giao diện (DOM) sau khi xử lý xong
                    if started_uploading:
                        print("  -> [✓] Quá trình xử lý upload dữ liệu trên Importer đã hoàn tất (thanh tiến trình đã đóng)!")
                        is_completed = True
                        break
            except Exception:
                pass

            time.sleep(0.5)

        # Nếu hoàn tất qua progress bar mà bảng chưa kịp in chi tiết, đợi thêm tối đa 3 giây để lấy log link từ bảng
        if is_completed and not completed_record:
            for _ in range(6):
                time.sleep(0.5)
                completed_record = find_completed_import_in_table(
                    importer_page,
                    target_filename=upload_file_path.name,
                    task_id=str(task_id) if task_id else None,
                    initial_item_ids=initial_item_ids
                )
                if completed_record and completed_record["is_success"]:
                    print(f"  -> [✓] Bảng Importer đã cập nhật bản ghi thành công (Item #{completed_record['item_id']}):")
                    print(f"       * Tên file:   {completed_record['filename']}")
                    print(f"       * Trạng thái: {completed_record['status']}")
                    break

        if not is_completed:
            print(f"\n[X] LỖI: Quá trình import file '{file_key}' trên Importer thất bại (dừng ở mức {last_percent} sau 5 phút).")
            return False, last_percent

        print("\n[✓] Quá trình import dữ liệu trên Importer đã hoàn tất!")
        return True, "100%"

    except Exception as e:
        print(f"  [X] Gặp sự cố ngoại lệ khi thao tác với Importer: {e}")
        return False, last_percent


class ImportSummaryTracker:
    """Quản lý và ghi nhận tình trạng thực thi của 2 lần import subtasks."""

    def __init__(self):
        self.results = {
            "layer1": {
                "name": "Import Tầng 1 (Cấu trúc Sprint)",
                "status": "Chưa thực hiện",
                "success": False
            },
            "layer2": {
                "name": "Import Tầng 2 (Chi tiết Work Items)",
                "status": "Chưa thực hiện",
                "success": False
            }
        }
        self.save_to_file()

    def update(self, layer: str, success: bool, status: str):
        if layer in self.results:
            self.results[layer]["success"] = success
            self.results[layer]["status"] = status
            self.save_to_file()

    def print_summary(self):
        print("\n" + "=" * 70)
        print("BÁO CÁO TÌNH TRẠNG IMPORT SUBTASKS")
        print("=" * 70)
        for key, info in self.results.items():
            icon = "[✓]" if info["success"] else ("[X]" if "Thất bại" in info["status"] else "[-]")
            print(f"  {icon} {info['name']}: {info['status']}")
        print("=" * 70 + "\n")

    def save_to_file(self, filename: str = "import_summary.txt"):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("======================================================================\n")
                f.write("BÁO CÁO TÌNH TRẠNG IMPORT SUBTASKS\n")
                f.write("======================================================================\n")
                for key, info in self.results.items():
                    icon = "[✓]" if info["success"] else ("[X]" if "Thất bại" in info["status"] else "[-]")
                    f.write(f"  {icon} {info['name']}: {info['status']}\n")
                f.write("======================================================================\n")
        except Exception:
            pass


def execute_import(
    importer_page: Page,
    milestone: dict,
    task_id: str,
    file_key: str,
    layer_name: str,
    lis_page: Page | None = None,
) -> tuple[bool, str]:
    """
    Thực hiện import đúng 1 lần duy nhất (không retry nếu gặp sự cố).
    Ghi nhận phần trăm (%) tại thời điểm hoàn thành hoặc gặp sự cố.
    Trả về: (is_success, status_message)
    """
    print(f"\n[*] Đang thực hiện {layer_name}...")
    try:
        success, stopped_percent = fill_importer_form(
            importer_page, milestone, task_id, file_key=file_key, lis_page=lis_page
        )
    except Exception as e:
        print(f"  [!] Lỗi bất thường trong quá trình import: {e}")
        success, stopped_percent = False, "0%"

    if success:
        status_msg = "Thành công"
        return True, status_msg

    print(f"\n[!] {layer_name} không thành công (dừng ở mức {stopped_percent}). Dừng tiến trình ngay lập tức (không thử lại).")
    status_msg = f"Thất bại (dừng ở mức {stopped_percent})"
    return False, status_msg


def execute_import_with_retry(
    importer_page: Page,
    milestone: dict,
    task_id: str,
    file_key: str,
    layer_name: str,
    lis_page: Page | None = None,
    max_retries: int = 0
) -> tuple[bool, int, str]:
    """
    Thực hiện import 1 lần duy nhất (không retry).
    Trả về: (is_success, total_attempts, status_message) với total_attempts = 1.
    """
    success, status_msg = execute_import(
        importer_page, milestone, task_id, file_key=file_key, layer_name=layer_name, lis_page=lis_page
    )
    return success, 1, status_msg

