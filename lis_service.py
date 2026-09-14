import re
from playwright.sync_api import Page
import config
from utils import (
    safe_goto,
    safe_input,
    check_form_error,
    select_option_with_fallback,
    get_sprint_name,
)


def verify_project_access(page: Page, proj_id: str, response=None) -> tuple[bool, str | None]:
    """
    Kiểm tra xem trang dự án LIS có truy cập hợp lệ hay bị lỗi (403 Forbidden, 404 Not Found, v.v.).
    Giúp phát hiện sớm lỗi nhập sai Project ID thay vì chờ đợi timeout ở các thao tác sau.
    Trả về: (is_accessible, error_message)
    """
    # 1. Kiểm tra HTTP Status Code nếu response khả dụng
    if response is not None:
        try:
            status = response.status
            if status == 403:
                return False, f"Lỗi HTTP 403 (Forbidden): Tài khoản không có quyền truy cập hoặc Project ID '{proj_id}' không hợp lệ."
            elif status == 404:
                return False, f"Lỗi HTTP 404 (Not Found): Dự án với Project ID '{proj_id}' không tồn tại trên hệ thống LIS."
            elif status >= 400:
                return False, f"Lỗi máy chủ HTTP {status} khi truy cập dự án #{proj_id}."
        except Exception:
            pass

    # 2. Kiểm tra Title của trang (Redmine thường đặt title là '403 - LIS' hoặc '404 - LIS')
    title = page.title().strip()
    title_lower = title.lower()
    if any(code in title for code in ["403", "404", "500"]) or any(kw in title_lower for kw in ["forbidden", "not found"]):
        if "403" in title or "forbidden" in title_lower:
            return False, f"Trang hiển thị lỗi 403 Forbidden: Tài khoản không có quyền truy cập hoặc Project ID '{proj_id}' không chính xác."
        elif "404" in title or "not found" in title_lower:
            return False, f"Trang hiển thị lỗi 404 Not Found: Dự án với Project ID '{proj_id}' không tồn tại trên hệ thống LIS."
        else:
            return False, f"Trang dự án phản hồi lỗi (Tiêu đề: '{title}')."

    # 3. Kiểm tra các thẻ thông báo lỗi trên giao diện Redmine / EasyRedmine
    try:
        error_elem = page.locator("#content h2, .wiki h2, #flash_error, .flash.error, .error").first
        if error_elem.count() > 0 and error_elem.is_visible():
            err_text = error_elem.inner_text().strip()
            if any(code in err_text for code in ["403", "404", "500"]) or any(kw in err_text.lower() for kw in ["forbidden", "not authorized", "not found", "không tìm thấy", "không có quyền"]):
                return False, f"Giao diện LIS báo lỗi: '{err_text}' (Project ID: #{proj_id})."
    except Exception:
        pass

    # 4. Kiểm tra cấu trúc menu dự án (Dự án hợp lệ luôn có ít nhất thanh menu hoặc tiêu đề dự án)
    try:
        project_nav = page.locator("#main-menu, #header h1, .project-name, #main_menu_top_project")
        if project_nav.count() == 0:
            return False, f"Không tìm thấy thanh điều hướng dự án #{proj_id}. Trang hiện tại có thể không phải trang dự án hợp lệ (Tiêu đề: '{title}')."
    except Exception:
        pass

    return True, None


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
