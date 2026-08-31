import os
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
import config
from login import login_and_save_session
from data_loader import load_milestone_from_file


# ============================================================
# HÀM TIỆN ÍCH DÙNG CHUNG (Helper Functions)
# ============================================================

def get_sprint_name(item: dict) -> str:
    """Lấy tên sprint/milestone từ dữ liệu JSON (hỗ trợ cả key cũ và mới)."""
    return item.get("Name Sprint") or item.get("Name", "Sprint mới")


def safe_goto(page_obj: Page, url: str, max_retries: int = 5, timeout: int = 60000):
    """Truy cập URL an toàn với cơ chế tự động thử lại khi gặp sự cố mạng (ERR_NETWORK_CHANGED, timeout, v.v.)."""
    for attempt in range(1, max_retries + 1):
        try:
            page_obj.goto(url, timeout=timeout, wait_until="load")
            return
        except Exception as e:
            print(f"[!] Cảnh báo mạng khi truy cập {url} (Lần thử {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)
            else:
                raise


def check_form_error(page: Page, entity_name: str) -> bool:
    """
    Kiểm tra lỗi phản hồi từ server LIS sau khi submit form.
    Trả về True nếu CÓ lỗi, False nếu thành công.
    """
    error_box = page.locator("#errorExplanation, #flash_error, .flash.error")
    if error_box.count() > 0 and error_box.first.is_visible():
        err_msg = error_box.first.inner_text().strip().replace("\n", " ")
        print(f"\n[X] TẠO {entity_name} THẤT BẠI - Server phản hồi lỗi: {err_msg}")
        return True
    return False


def select_option_with_fallback(locator, label: str, field_name: str) -> bool:
    """
    Chọn giá trị dropdown: thử khớp chính xác trước, fallback regex nếu cần.
    Trả về True nếu chọn được, False nếu thất bại.
    """
    try:
        locator.select_option(label=label)
        print(f"  -> [✓] Đã chọn {field_name}: '{label}'")
        return True
    except Exception:
        try:
            locator.select_option(label=re.compile(re.escape(label), re.I))
            print(f"  -> [✓] Đã chọn {field_name} khớp: '{label}'")
            return True
        except Exception as ex:
            print(f"  [!] Không thể chọn {field_name}: {ex}")
            return False


def set_project_settings(page: Page, planned: bool, public: bool, settings_url: str | None = None) -> bool:
    """
    Vào Settings và cấu hình Planned / Public cho dự án.
    Tái sử dụng cho cả 2 lần: trước Import (Planned=True, Public=False)
    và sau Import (Planned=False, Public=True).
    """
    planned_label = "BẬT" if planned else "TẮT"
    public_label = "BẬT" if public else "TẮT"
    print(f"\n[*] Đang vào mục 'Settings' để cấu hình: Planned = {planned_label}, Public = {public_label}...")

    # 1. Điều hướng thẳng tới URL Settings nếu có sẵn
    if settings_url:
        safe_goto(page, settings_url)
    elif "settings" not in page.url:
        settings_selector = "#main-menu a[href*='settings'], #main-menu a:has-text('Settings'), a.settings, a[href*='/settings']"
        settings_tab = page.locator(settings_selector).first

        if settings_tab.count() > 0:
            try:
                href = settings_tab.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        href = f"{config.LIS_HOME_URL.rstrip('/')}{href}"
                    safe_goto(page, href)
            except Exception:
                pass

        if "settings" not in page.url:
            match = re.search(r"/projects/([^/?]+)", page.url)
            if match:
                safe_goto(page, f"{config.LIS_HOME_URL.rstrip('/')}/projects/{match.group(1)}/settings")

    page.wait_for_load_state("networkidle")
    print(f"[✓] Đã chuyển tới trang Settings: {page.url}")

    # 2. Cấu hình ô Planned
    planned_checkbox = page.locator("#project_is_planned")
    try:
        planned_checkbox.wait_for(state="attached", timeout=10000)
        planned_checkbox.set_checked(planned)
        print(f"  -> [✓] Ô 'Planned': {'ĐƯỢC CHỌN' if planned else 'KHÔNG CHỌN'}")
    except Exception as e:
        print(f"  [!] Cảnh báo khi cấu hình ô 'Planned': {e}")

    # 3. Cấu hình ô Public
    public_checkbox = page.locator("#project_is_public")
    if public_checkbox.count() > 0:
        try:
            if public_checkbox.first.is_visible(timeout=3000):
                public_checkbox.set_checked(public)
                print(f"  -> [✓] Ô 'Public': {'ĐƯỢC CHỌN' if public else 'KHÔNG CHỌN'}")
        except Exception:
            print("  [!] Không tìm thấy ô 'Public' trên giao diện.")

    # 4. Bấm Save
    save_btn = page.locator(
        "form[action*='settings'] input[type='submit'], "
        "#tab-content-info input[type='submit'], "
        "input[type='submit'][value='Save']"
    ).first
    if save_btn.count() > 0:
        print("  [*] Đang bấm nút 'Save' để lưu cài đặt...")
        try:
            save_btn.click()
            page.wait_for_load_state("networkidle")
            print("  -> [✓] Đã lưu cài đặt dự án thành công!")
        except Exception as e:
            print(f"  [!] Cảnh báo khi bấm Save settings: {e}")

    return True


def safe_input(prompt: str, default: str = "") -> str:
    """Gọi input() an toàn — trả về default nếu headless hoặc không có stdin."""
    if config.HEADLESS or not sys.stdin.isatty():
        return default
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return default


# ============================================================
# CÁC HÀM ĐIỀN FORM
# ============================================================

def fill_milestone_form(page: Page, item: dict) -> bool:
    """
    Điền các thông tin từ file JSON vào form New Milestone trên LIS.
    Sử dụng trực tiếp ID chính xác 100% của từng ô nhập liệu:
      - Name                    -> #version_name
      - Release Start Date      -> #version_custom_field_values_208
      - Release Submission Date -> #version_effective_date
      - Release Type            -> #version_custom_field_values_60
      - Environment             -> #version_custom_field_values_88
      - Submit Button           -> input[name="commit"][value="Create"]
    """
    milestone_name = get_sprint_name(item)
    print(f"\n[*] Đang tiến hành điền form milestone: '{milestone_name}'...")

    # 1. Name (ID: version_name)
    if milestone_name:
        page.locator("#version_name").fill(milestone_name)
        print(f"  -> [✓] Đã điền Name: '{milestone_name}'")

    # 2. Release Start Date (ID: version_custom_field_values_208)
    if item.get("Release Start Date"):
        page.locator("#version_custom_field_values_208").fill(item["Release Start Date"])
        print(f"  -> [✓] Đã điền Release Start Date: '{item['Release Start Date']}'")

    # 3. Release Submission Date (ID: version_effective_date)
    if item.get("Release Submission Date"):
        page.locator("#version_effective_date").fill(item["Release Submission Date"])
        print(f"  -> [✓] Đã điền Release Submission Date: '{item['Release Submission Date']}'")

    # 4. Release Type (Dropdown - ID: version_custom_field_values_60)
    if item.get("Release Type"):
        page.locator("#version_custom_field_values_60").select_option(item["Release Type"])
        print(f"  -> [✓] Đã chọn Release Type: '{item['Release Type']}'")

    # 5. Environment (Dropdown - ID: version_custom_field_values_88)
    if item.get("Environment"):
        page.locator("#version_custom_field_values_88").select_option(item["Environment"])
        print(f"  -> [✓] Đã chọn Environment: '{item['Environment']}'")

    # 6. Bấm nút Tạo (Create)
    print("  [*] Đang bấm nút tạo milestone...")
    page.locator('input[type="submit"][name="commit"][value="Create"]').click()
    page.wait_for_load_state("networkidle")

    # 7. Kiểm tra kết quả phản hồi từ server LIS
    if check_form_error(page, "MILESTONE"):
        if "already been taken" in page.locator("#errorExplanation").inner_text().lower():
            print(f"  👉 Nguyên nhân: Tên Milestone '{milestone_name}' ĐÃ TỒN TẠI trên dự án.")
            print("  👉 Cách xử lý: Vui lòng đổi giá trị 'Name Sprint' trong file JSON sang tên khác rồi chạy lại.")
        return False

    print(f"\n[✓] Đã tạo thành công milestone '{milestone_name}'!")
    return True


def fill_sprint_form(page: Page, item: dict) -> bool:
    """
    Điền thông tin vào form New Sprint trên LIS sử dụng trực tiếp ID chính xác:
      - Sprint Name -> #easy_sprint_name
      - Start date  -> #_easy_sprint_start_date
      - Due date    -> #_easy_sprint_due_date
      - Milestone   -> #easy_sprint_version_id (Dropdown)
      - Submit      -> input[name="commit"][value="Create"]
    """
    sprint_name = get_sprint_name(item)
    print(f"\n[*] Đang tiến hành điền form Sprint: '{sprint_name}'...")

    # 1. Name (ID: easy_sprint_name)
    if sprint_name:
        page.locator("#easy_sprint_name").fill(sprint_name)
        print(f"  -> [✓] Đã điền Sprint Name: '{sprint_name}'")

    # 2. Start date (ID: _easy_sprint_start_date)
    if item.get("Release Start Date"):
        page.locator("#_easy_sprint_start_date").fill(item["Release Start Date"])
        print(f"  -> [✓] Đã điền Start date: '{item['Release Start Date']}'")

    # 3. Due date (ID: _easy_sprint_due_date)
    if item.get("Release Submission Date"):
        page.locator("#_easy_sprint_due_date").fill(item["Release Submission Date"])
        print(f"  -> [✓] Đã điền Due date: '{item['Release Submission Date']}'")

    # 4. Milestone (Dropdown - ID: easy_sprint_version_id)
    if sprint_name:
        select_option_with_fallback(
            page.locator("#easy_sprint_version_id"),
            sprint_name,
            "Milestone"
        )

    # 5. Bấm nút Create
    print("  [*] Đang bấm nút tạo Sprint...")
    page.locator('input[type="submit"][name="commit"][value="Create"]').click()
    page.wait_for_load_state("networkidle")

    # 6. Kiểm tra kết quả phản hồi từ server
    if check_form_error(page, "SPRINT"):
        return False

    print(f"\n[✓] Đã tạo thành công Sprint '{sprint_name}'!")
    return True


def select_assignee_smartly(page: Page, assignee_val: str):
    """
    Chọn Assignee thông minh:
      1. Khớp chính xác 100%.
      2. Nếu không khớp 100%, tự động lọc các thành viên gần đúng (fuzzy match).
      3. Nếu chỉ có 1 người khớp gần đúng -> Tự động chọn luôn.
      4. Nếu có nhiều người khớp -> Hiện menu rút gọn [1, 2, 3...] để chọn tại terminal.
      5. Nếu không khớp ai -> Cho phép gán cho << me >> hoặc gõ từ khóa khác.
    """
    assignee_select = page.locator("#issue_assigned_to_id")
    assignee_select.wait_for(state="visible", timeout=10000)

    # 1. Thử khớp chính xác
    try:
        assignee_select.select_option(label=assignee_val)
        print(f"  -> [✓] Đã chọn chính xác Assignee: '{assignee_val}'")
        return
    except Exception:
        pass

    # 2. Lấy toàn bộ danh sách thành viên từ dropdown
    options = [opt.strip() for opt in assignee_select.locator("option").all_inner_texts() if opt.strip()]

    # 3. Lọc danh sách gần đúng theo từ khóa
    tokens = [t.lower() for t in re.split(r"[\s\-_]+", assignee_val) if t]
    matches = []
    for opt in options:
        opt_lower = opt.lower()
        if assignee_val.lower() in opt_lower:
            matches.append(opt)
        elif any(tok in opt_lower for tok in tokens if len(tok) > 1):
            if opt not in matches:
                matches.append(opt)

    # 4. Xử lý các trường hợp kết quả tìm kiếm
    if len(matches) == 1:
        # Chỉ có duy nhất 1 người khớp gần đúng -> Tự động chọn luôn
        selected_person = matches[0]
        assignee_select.select_option(label=selected_person)
        print(f"  -> [✓] Tự động chọn thành viên phù hợp nhất: '{selected_person}' (khớp từ '{assignee_val}')")
    elif len(matches) > 1:
        # Có nhiều người gần giống -> Cho người dùng chọn nhanh số thứ tự
        print(f"\n  [!] Không tìm thấy chính xác '{assignee_val}'. Tìm thấy {len(matches)} thành viên tương tự:")
        for idx, opt in enumerate(matches, 1):
            print(f"      [{idx}] {opt}")

        chosen_opt = matches[0]
        user_choice = safe_input(f"  👉 Nhập số [1-{len(matches)}] để chọn (mặc định [1]): ")
        if user_choice.isdigit() and 1 <= int(user_choice) <= len(matches):
            chosen_opt = matches[int(user_choice) - 1]

        assignee_select.select_option(label=chosen_opt)
        print(f"  -> [✓] Đã chọn Assignee: '{chosen_opt}'")
    else:
        # Không tìm thấy ai -> Gợi ý gán cho << me >> hoặc nhập lại
        print(f"\n  [!] Không tìm thấy thành viên nào khớp với '{assignee_val}' trong dự án.")
        default_me = next((opt for opt in options if "me" in opt.lower()), None)
        fallback_person = default_me if default_me else (options[0] if options else None)

        user_input = safe_input(f"  👉 Bấm ENTER để gán cho '{fallback_person}' (hoặc gõ từ khóa tên khác): ")
        if user_input:
            retry_matches = [opt for opt in options if user_input.lower() in opt.lower()]
            if retry_matches:
                fallback_person = retry_matches[0]

        if fallback_person:
            assignee_select.select_option(label=fallback_person)
            print(f"  -> [✓] Đã chọn Assignee: '{fallback_person}'")


def extract_task_id(page: Page) -> str | None:
    """
    Trích xuất mã Task ID (ví dụ: 484861) từ giao diện hoặc URL sau khi tạo Task thành công.
    """
    task_id = None

    # 1. Bóc tách từ tiêu đề task (span[data-name='issue[subject]'] chứa text: '#484861 - ...')
    subject_elem = page.locator("span[data-name='issue[subject]'], .issue_subject, h2, h3").first
    if subject_elem.count() > 0:
        try:
            text = subject_elem.inner_text()
            match = re.search(r"#(\d+)", text)
            if match:
                task_id = match.group(1)
        except Exception:
            pass

    # 2. Bóc tách từ URL hiện tại (/issues/484861 hoặc /easy_issues/484861)
    if not task_id:
        url_match = re.search(r"/(?:easy_)?issues/(\d+)", page.url)
        if url_match:
            task_id = url_match.group(1)

    # 3. Bóc tách từ liên kết favorite (/easy_issues/484861/favorite)
    if not task_id:
        fav_link = page.locator("a[href*='favorite']").first
        if fav_link.count() > 0:
            href = fav_link.get_attribute("href") or ""
            fav_match = re.search(r"/easy_issues/(\d+)/", href)
            if fav_match:
                task_id = fav_match.group(1)

    if task_id:
        print(f"  -> [✓] Đã lưu biến tạm Task ID: {task_id}")
    else:
        print("  -> [!] Chưa trích xuất được Task ID từ màn hình.")

    return task_id


def extract_work_items_task_id(page: Page) -> str | None:
    """
    Trích xuất Task ID của task con 'WORK ITEMS' (ví dụ: 485037) từ bảng Subtasks trên LIS.

    Chuẩn thiết kế bền vững (Design Pattern):
      1. Ưu tiên 1 (Khuyên dùng): Lấy từ thuộc tính `href` (/issues/<ID>) vì URL định tuyến của Redmine
         là cố định 100% ở backend, không bao giờ bị ảnh hưởng bởi thay đổi giao diện/ngôn ngữ.
      2. Ưu tiên 2 (Fallback UI): Bóc tách số từ nội dung hiển thị (inner_text).
      3. Xử lý Exception: Bao bọc an toàn, cho phép nhập tay tại terminal nếu mạng lag thay vì crash script.
    """
    work_items_id = None
    # Scope selector vào bảng subtasks thay vì toàn bộ trang
    selector = (
        "#issue_tree td.subject a:has-text('WORK ITEMS'), "
        "table.subtasks td.subject a:has-text('WORK ITEMS'), "
        "a[href*='issues']:has-text('WORK ITEMS')"
    )

    try:
        # Chờ phần tử có mặt trong cây DOM (timeout 15s)
        page.wait_for_selector(selector, state="attached", timeout=15000)
        link_elem = page.locator(selector).first

        # Ưu tiên 1: Thuộc tính href (/issues/485037?project=false hoặc /easy_issues/485037)
        href = link_elem.get_attribute("href") or ""
        match_href = re.search(r"/(?:easy_)?issues/(\d+)", href)
        if match_href:
            work_items_id = match_href.group(1)

        # Ưu tiên 2: Bóc tách từ nội dung hiển thị (Text fallback)
        if not work_items_id:
            text = link_elem.inner_text().strip()
            match_text = re.search(r"#?(\d+)", text)
            if match_text:
                work_items_id = match_text.group(1)

    except Exception as ex:
        print(f"  [!] Cảnh báo khi tự động dò tìm task 'WORK ITEMS': {ex}")

    # Xử lý an toàn: Nếu không tìm thấy, cho phép nhập tay thay vì crash script
    if work_items_id:
        print(f"  -> [✓] Đã trích xuất và lưu Task ID của 'WORK ITEMS': #{work_items_id}")
    else:
        print("\n  [!] Không tìm thấy task 'WORK ITEMS' tự động trên màn hình.")
        user_input = safe_input("  👉 Vui lòng nhập tay Task ID của WORK ITEMS (hoặc bấm ENTER để bỏ qua): ")
        if user_input.isdigit():
            work_items_id = user_input
            print(f"  -> [✓] Đã nhận Task ID nhập tay: #{work_items_id}")

    return work_items_id


def fill_task_form(page: Page, item: dict) -> tuple[bool, str | None]:
    """
    Điền các thông tin vào form New Task trên LIS:
      - Subject                -> #issue_subject               (Giá trị từ 'Name Sprint')
      - Assignee               -> #issue_assigned_to_id        (Giá trị từ 'Assignee')
      - Target version         -> #issue_fixed_version_id      (Giá trị từ 'Name Sprint')
      - Start date             -> #issue_start_date            (Giá trị từ 'Release Start Date')
      - Due date               -> #issue_due_date              (Giá trị từ 'Release Submission Date')
      - Sprint                 -> #issue_easy_sprint_id        (Giá trị từ 'Name Sprint')
    """
    task_subject = get_sprint_name(item)
    print(f"\n[*] Đang tiến hành điền form Task: '{task_subject}'...")

    # 1. Subject (ID: issue_subject)
    if task_subject:
        page.locator("#issue_subject").wait_for(state="visible", timeout=10000)
        page.locator("#issue_subject").fill(task_subject)
        print(f"  -> [✓] Đã điền Subject: '{task_subject}'")

    # 2. Assignee (Dropdown thông minh - ID: issue_assigned_to_id)
    if item.get("Assignee"):
        select_assignee_smartly(page, item["Assignee"])

    # 3. Target version / Milestone (Dropdown - ID: issue_fixed_version_id)
    if task_subject:
        version_select = page.locator("#issue_fixed_version_id")
        version_select.wait_for(state="visible", timeout=10000)
        select_option_with_fallback(version_select, task_subject, "Target version")

    # 4. Start date (ID: issue_start_date)
    if item.get("Release Start Date"):
        page.locator("#issue_start_date").wait_for(state="visible", timeout=10000)
        page.locator("#issue_start_date").fill(item["Release Start Date"])
        print(f"  -> [✓] Đã điền Start date: '{item['Release Start Date']}'")

    # 5. Due date (ID: issue_due_date)
    if item.get("Release Submission Date"):
        page.locator("#issue_due_date").wait_for(state="visible", timeout=10000)
        page.locator("#issue_due_date").fill(item["Release Submission Date"])
        print(f"  -> [✓] Đã điền Due date: '{item['Release Submission Date']}'")

    # 6. Sprint (Dropdown - ID: issue_easy_sprint_id)
    if task_subject:
        sprint_select = page.locator("#issue_easy_sprint_id")
        sprint_select.wait_for(state="visible", timeout=10000)
        select_option_with_fallback(sprint_select, task_subject, "Sprint")

    # 7. Bấm nút Create (Submit form Task)
    print("  [*] Đang bấm nút 'Create' để tạo Task...")
    submit_task_btn = page.locator('input[type="submit"][name="commit"][value="Create"]').first
    submit_task_btn.click()
    page.wait_for_load_state("networkidle")

    # 8. Kiểm tra phản hồi từ server
    if check_form_error(page, "TASK"):
        return False, None

    # 9. Trích xuất và lưu Task ID
    created_task_id = extract_task_id(page)
    if not created_task_id:
        print(f"\n[X] LỖI: Không thể trích xuất Task ID của Task '{task_subject}' sau khi tạo!")
        return False, None

    print(f"\n[✓] Đã tạo thành công Task '{task_subject}' (Task ID: #{created_task_id})!")
    return True, created_task_id


def fill_importer_form(importer_page: Page, item: dict, task_id: str, file_key: str) -> bool:
    """
    Điền các thông tin vào form trên trang Importer (https://importer.larion.com/):
      1. Project ID                    -> #inputProject (từ 'Project ID Importer')
      2. Parent Task/Issue ID          -> input[name='issueId'] (từ biến task_id)
      3. Author                        -> input[name='author'] (từ 'Author Importer')
      4. File Type                     -> Radio 'Google Doc' (bỏ chọn 'MS-Project')
      5. Upload file                   -> File cấu hình bắt buộc từ JSON (theo file_key)
      6. Checkbox Project Status       -> input[ng-model='project_planing']
    """
    print(f"\n[*] Đang tiến hành điền form trên trang Importer (Target Task ID: #{task_id})...")

    # Kiểm tra file upload trước khi điền form để tránh mất thời gian nếu thiếu file
    upload_filename = item.get(file_key)
    if not upload_filename:
        print(f"\n[X] LỖI CẤU HÌNH: Không tìm thấy trường '{file_key}' trong file JSON dữ liệu!")
        return False

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
        return False

    # Đảm bảo file upload luôn có phần mở rộng .xlsx hoặc .xls hợp lệ để Importer không bị nghẽn
    if upload_file_path.suffix.lower() not in [".xlsx", ".xls"]:
        import shutil
        valid_excel_path = upload_file_path.parent / f"{upload_file_path.stem}.xlsx"
        try:
            shutil.copy2(upload_file_path, valid_excel_path)
            upload_file_path = valid_excel_path
            print(f"  [*] Đã chuyển đổi tên file tạm sang chuẩn Excel: '{upload_file_path.name}'")
        except Exception:
            pass

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

    # 3. Author Importer
    author_importer = item.get("Author Importer", config.LIS_USERNAME or "")
    if author_importer:
        author_input = importer_page.locator("input[name='author'], input[placeholder*='Redmine Login']").first
        author_input.wait_for(state="visible", timeout=10000)
        author_input.fill(str(author_importer))
        author_input.dispatch_event("input")
        author_input.dispatch_event("change")
        author_input.press("Tab")
        print(f"  -> [✓] Đã điền Author: '{author_importer}'")

    # 4. Chọn Radio 'Google Doc' (bỏ chọn MS-Project)
    google_doc_radio = importer_page.locator("input[type='radio'][value='google-doc']").first
    google_doc_radio.wait_for(state="attached", timeout=10000)
    google_doc_radio.check()
    print("  -> [✓] Đã tick chọn 'Google Doc' (và không chọn 'MS-Project')")

    # 5. Upload file từ đường dẫn đã kiểm tra ở trên
    file_input = importer_page.locator("#inputFile, input[type='file'][name='file'], input[type='file']").first
    file_input.set_input_files(str(upload_file_path))
    print(f"  -> [✓] Đã upload file cấu hình ({file_key}): '{upload_file_path.name}'")

    # 6. Tích chọn ô Checkbox "I already set Project Status to 'planing'"
    planning_checkbox = importer_page.locator("input[ng-model='project_planing'], input[type='checkbox']").first
    planning_checkbox.wait_for(state="visible", timeout=10000)
    planning_checkbox.set_checked(True)
    print("  -> [✓] Đã tick chọn ô 'I already set Project Status to planing'")

    # 7. Bấm nút Submit và chờ thanh Progress Bar đạt 100%
    print("  [*] Đang bấm nút 'Submit' trên Importer...")
    submit_btn = importer_page.locator("button.btn-primary, button[type='submit']").filter(has_text="Submit").first

    # Đợi nút Submit được mở khóa (enabled)
    try:
        importer_page.wait_for_function(
            "() => { const btn = document.querySelector('button.btn-primary, button[type=\"submit\"]'); return btn && !btn.disabled; }",
            timeout=15000
        )
    except Exception:
        pass

    submit_btn.click()
    print("  [*] Đã bấm Submit. Đang theo dõi tiến trình upload (chờ thanh tiến trình đạt 100%)...")

    # Theo dõi thanh progress bar theo thời gian thực cho đến khi hoàn tất (tối đa 5 phút)
    start_time = time.time()
    last_percent = ""
    is_completed = False
    started_uploading = False

    while time.time() - start_time < 300:
        progress_bar = importer_page.locator(".progress .progress-bar")
        progress_container = importer_page.locator(".progress")

        if progress_bar.count() > 0:
            text = progress_bar.first.inner_text().strip()
            aria_val = progress_bar.first.get_attribute("aria-valuenow")
            is_visible = progress_container.first.is_visible() if progress_container.count() > 0 else False

            # In phần trăm tiến độ khi có số thay đổi (e.g. 20%, 25%, ...)
            match_num = re.search(r"\d+%", text)
            if match_num and text != last_percent:
                last_percent = text
                started_uploading = True
                print(f"  -> Tiến độ import: {text}")

            # Điều kiện 1: Đạt đúng 100%
            if "100%" in text or aria_val == "100":
                print("  -> [✓] Thanh tiến trình đã đạt 100% hoàn tất!")
                is_completed = True
                break

            # Điều kiện 2: Sau khi đã chạy tiến độ, server xử lý xong và AngularJS ẩn/reset thanh tiến trình về '%'
            if started_uploading and (text == "%" or not is_visible):
                print("  -> [✓] Quá trình xử lý upload dữ liệu trên Importer đã hoàn tất 100%!")
                is_completed = True
                break

        # Kiểm tra thông báo kết quả (Alert / Result) nếu có
        alert_box = importer_page.locator(".alert-success, .alert, .result")
        if alert_box.count() > 0 and alert_box.first.is_visible():
            alert_text = alert_box.first.inner_text().strip().replace("\n", " ")
            print(f"  -> [✓] Phản hồi từ Importer: {alert_text}")
            is_completed = True
            break

        time.sleep(0.5)

    if not is_completed:
        print(f"\n[X] LỖI: Quá trình import file '{file_key}' trên Importer thất bại (không đạt 100% sau thời gian chờ tối đa 5 phút).")
        return False

    print("\n[✓] Quá trình import dữ liệu trên Importer đã hoàn tất!")
    return True


# ============================================================
# HÀM CHÍNH
# ============================================================

def run_automation(data_file_path: str | None = None):
    """Chạy toàn bộ quy trình tự động hóa LIS + Importer."""

    # 1. Đọc dữ liệu sprint / milestone từ file hoặc biến môi trường Jenkins
    try:
        milestone = load_milestone_from_file(data_file_path)
        sprint_name = get_sprint_name(milestone)
        print(f"[✓] Đã nạp thành công dữ liệu Sprint: '{sprint_name}'")
    except Exception as e:
        print(f"[X] LỖI NẠP THÔNG TIN SPRINT: {e}")
        sys.exit(1)

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
        # Thao tác 1: Nhập "MAX" vào ô "Type to jump to project..."
        # ==========================================
        print("[*] Đang tìm ô tìm kiếm dự án 'Type to jump to project...'...")
        project_input = page.get_by_placeholder("Type to jump to project...", exact=False)
        if project_input.count() == 0:
            project_input = page.locator("input[placeholder*='jump to project' i], input[placeholder*='Type to jump' i]")

        project_input.wait_for(state="visible", timeout=10000)
        project_input.click()
        project_input.fill("MAX")
        print("[✓] Đã nhập thành công chữ 'MAX' vào ô tìm kiếm dự án.")

        # ==========================================
        # Thao tác 2: Nhấp vào ô "Delivery >> Bestarion >> Projects >> MAX"
        # ==========================================
        print("[*] Đang đợi danh sách gợi ý xuất hiện và tìm 'Delivery >> Bestarion >> Projects >> MAX'...")
        target_pattern = re.compile(r"Delivery.*Bestarion.*Projects.*MAX", re.IGNORECASE)
        target_option = page.locator("li, a, div, span, .ui-menu-item").filter(has_text=target_pattern).first

        target_option.wait_for(state="visible", timeout=10000)
        print(f"[*] Đã tìm thấy mục: '{target_option.inner_text().strip()}'. Đang click...")
        target_option.click()
        page.wait_for_load_state("networkidle")
        print(f"[✓] Đã chuyển đến trang dự án: {page.title()} ({page.url})")

        # Lưu lại URL trang Settings của dự án để dùng xuyên suốt
        project_settings_url = None
        match = re.search(r"/projects/([^/?]+)", page.url)
        if match:
            project_settings_url = f"{config.LIS_HOME_URL.rstrip('/')}/projects/{match.group(1)}/settings"
            print(f"[✓] Đã ghi nhớ đường dẫn Settings của dự án: {project_settings_url}")

        # ==========================================
        # Thao tác 3: Vào Roadmap
        # ==========================================
        print("[*] Đang vào mục 'Roadmap'...")
        roadmap_link = page.locator("a, button, li").filter(has_text=re.compile(r"^Roadmap$", re.IGNORECASE)).first
        if roadmap_link.count() == 0:
            roadmap_link = page.locator("a:has-text('Roadmap'), .roadmap, a[href*='roadmap']")

        roadmap_link.wait_for(state="visible", timeout=10000)
        roadmap_link.click()
        page.wait_for_load_state("networkidle")
        print(f"[✓] Đã vào trang Roadmap: {page.title()}")

        # ==========================================
        # Thao tác 4: Bấm 'New milestone'
        # ==========================================
        print("[*] Đang nhấp vào 'New milestone'...")
        new_milestone_btn = page.locator("a, button").filter(has_text=re.compile(r"New\s+milestone", re.IGNORECASE)).first
        if new_milestone_btn.count() == 0:
            new_milestone_btn = page.locator("a[href*='versions/new'], a[href*='milestone']")

        new_milestone_btn.wait_for(state="visible", timeout=10000)
        new_milestone_btn.click()
        page.wait_for_load_state("networkidle")

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
        if not fill_importer_form(importer_page, milestone, task_id, file_key="Upload File"):
            print("\n[X] DỪNG QUY TRÌNH: Import Tầng 1 (Structure Template) thất bại.")
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

        if not fill_importer_form(importer_page, milestone, work_items_task_id, file_key="Upload Work Items File"):
            print("\n[X] DỪNG QUY TRÌNH: Import Tầng 2 (Work Items Detail) thất bại.")
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
        # Hoàn tất
        # ==========================================
        print(f"\n[✓] HOÀN THÀNH TOÀN BỘ QUY TRÌNH TỰ ĐỘNG HÓA THÀNH CÔNG RỰC RỠ!")
        print(f"    - Parent Task ID:     #{task_id}")
        print(f"    - WORK ITEMS Task ID: #{work_items_task_id}")
        print(f"    - Cài đặt dự án:      Public = Checked | Planned = Unchecked")

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
