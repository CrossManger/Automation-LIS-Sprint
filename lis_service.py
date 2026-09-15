import os
import re
import time
import json
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


def fill_date_filter_range(page: Page, field_name: str, date_value: str) -> None:
    """
    Điền dải ngày (From / To) cho một bộ lọc cụ thể (start_date hoặc due_date):
      - Cả From và To đều nhận date_value.
      - Tích chọn radio button kỳ thứ 2 (#<field_name>_date_period_2).
    """
    friendly_label = "Ngày bắt đầu (Start date)" if "start" in field_name.lower() else "Ngày kết thúc (Due date)"
    print(f"\n[*] Đang thiết lập dải ngày cho '{friendly_label}'...")
    from_input = page.locator(f"#{field_name}_from")
    from_input.wait_for(state="visible", timeout=10000)
    from_input.scroll_into_view_if_needed()

    page.evaluate(f"""() => {{
        const radio = document.querySelector('#{field_name}_date_period_2');
        if (radio) {{
            radio.checked = true;
            radio.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        const fromInp = document.querySelector('#{field_name}_from');
        if (fromInp) {{
            fromInp.value = '{date_value}';
            fromInp.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        const toInp = document.querySelector('#{field_name}_to');
        if (toInp) {{
            toInp.value = '{date_value}';
            toInp.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }}""")
    time.sleep(0.5)

    radio_locator = page.locator(f"#{field_name}_date_period_2")
    if radio_locator.count() > 0 and not radio_locator.is_checked():
        radio_locator.check()

    print(f"  -> [✓] Đã chọn dải ngày cho {friendly_label}: {date_value}")


def get_expected_task_count(page: Page) -> int | None:
    """
    Trích xuất tổng số lượng tasks kỳ vọng từ tiêu đề danh sách hoặc phân trang trên giao diện LIS.
    Ưu tiên 1: Đọc từ tiêu đề bảng (ví dụ: 'Task list 83' hoặc 'Task list (83)').
    Ưu tiên 2: Đọc từ thẻ phân trang (.pagination, ví dụ: '(1-25/83)').
    """
    # 1. Quét qua tiêu đề danh sách
    try:
        heading_locators = page.locator("h2, .easy-query-heading, #content h2")
        for i in range(heading_locators.count()):
            text = heading_locators.nth(i).inner_text().strip()
            m = re.search(r"Task list\s*\(?(\d+)\)?", text, re.IGNORECASE)
            if m:
                return int(m.group(1))
    except Exception:
        pass

    # 2. Quét qua thẻ phân trang nếu có
    try:
        pag_locators = page.locator(".pagination, span.pagination")
        for i in range(pag_locators.count()):
            text = pag_locators.nth(i).inner_text().strip()
            m = re.search(r"/\s*(\d+)", text)
            if m:
                return int(m.group(1))
    except Exception:
        pass

    return None


def scroll_and_load_all_tasks(page: Page, max_scroll_attempts: int = 40) -> int:
    """
    Cuộn trang liên tục đến khi toàn bộ tasks được nạp qua Infinite scroll.
    Sử dụng cơ chế CHỜ ĐỘNG (page.wait_for_function) theo sự kiện DOM thay vì sleep cứng,
    hoàn toàn không bị phụ thuộc vào tốc độ mạng hay thời gian phản hồi của server.
    """
    print("\n  [*] Cuộn chuột nạp toàn bộ danh sách tasks (Infinite scroll)...")
    total_expected = get_expected_task_count(page)
    if total_expected is not None:
        print(f"  [*] Tổng số tasks kỳ vọng từ hệ thống: {total_expected}")

    last_count = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").count()
    stable_retries = 0

    for scroll_idx in range(1, max_scroll_attempts + 1):
        # Nếu đã nạp đủ số lượng kỳ vọng, dừng ngay lập tức
        if total_expected is not None and last_count >= total_expected:
            break

        # 1. Kích hoạt cuộn phần tử cuối cùng vào tầm nhìn (trigger Waypoint / Intersection Observer)
        last_item = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").last
        if last_item.count() > 0:
            try:
                last_item.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

        # 2. Cuộn đáy các container
        page.evaluate("""() => {
            window.scrollTo(0, document.body.scrollHeight);
            const containers = document.querySelectorAll('.autoscroll, #content, .table-container, .easy-query-table-container');
            containers.forEach(c => { c.scrollTop = c.scrollHeight; });
        }""")

        # 3. Giả lập cuộn chuột thật
        page.mouse.wheel(0, 2000)

        # 4. CHỜ ĐỘNG: Đợi số lượng hàng trong DOM thực sự tăng lên so với last_count
        # Cho phép chờ tối đa 8 giây cho MỖI đợt nạp (server phản hồi lúc nào thì tiếp tục ngay lúc đó)
        try:
            page.wait_for_function(
                f"() => document.querySelectorAll('table.issues tbody tr.issue, table.list.issues tbody tr').length > {last_count}",
                timeout=8000
            )
            current_count = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").count()
            print(f"  -> Đã nạp được {current_count}/{total_expected or '?'} tasks...")
            last_count = current_count
            stable_retries = 0
        except Exception:
            # Nếu sau 8 giây mà số lượng chưa tăng
            current_count = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").count()
            if current_count > last_count:
                last_count = current_count
                stable_retries = 0
            else:
                stable_retries += 1
                # Nếu đã biết mục tiêu mà chưa đạt, kiên nhẫn thử lại tối đa 3 lần (3 x 8s = 24 giây)
                max_retries = 3 if (total_expected and last_count < total_expected) else 2
                if stable_retries >= max_retries:
                    print(f"  [!] Đã thử kích hoạt cuộn {stable_retries} lần liên tiếp nhưng không có thêm task mới.")
                    break
                print(f"  [*] Đang chờ server nạp thêm đợt tasks mới (thử lại lần {stable_retries}/{max_retries})...")

    total_tasks = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").count()
    print(f"  [✓] Tổng số tasks đã nạp vào bảng: {total_tasks}/{total_expected or total_tasks}")
    return total_tasks


def select_all_tasks_context_menu(page: Page) -> int:
    """
    Chọn tất cả các tasks trong bảng và đánh dấu class context-menu-selection
    để Easy Redmine Context Menu nhận diện đúng toàn bộ tasks được chọn.
    Sử dụng hoàn toàn DOM API thuần túy, không phụ thuộc vào window.jQuery.
    """
    print("  [*] Chọn tất cả tasks trên bảng...")
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        const checkAllBtn = document.querySelector('th.checkbox a, th a.icon-checked, th a[onclick*="toggleIssuesSelection"]');
        if (checkAllBtn && typeof window.toggleIssuesSelection === 'function') {
            try { window.toggleIssuesSelection(checkAllBtn); } catch(e) {}
        }
        const rows = document.querySelectorAll('table.issues tbody tr.hascontextmenu, table.issues tbody tr.issue');
        rows.forEach(tr => {
            tr.classList.add('context-menu-selection');
            const cb = tr.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = true;
        });
    }""")
    time.sleep(0.5)
    checked_count = page.locator("table.issues tbody tr input[type='checkbox']:checked, tr.issue input[type='checkbox']:checked").count()
    print(f"  [✓] Đã chọn {checked_count} tasks.")
    return checked_count


def open_context_menu_safe(page: Page) -> None:
    """
    Mở Context Menu an toàn:
      - Ẩn context menu cũ (nếu có).
      - Right-click vào ô checkbox của task đầu tiên có cờ selection.
      - Chờ request AJAX /issues/context_menu hoàn thành và #context-menu hiển thị.
    """
    print("  [*] Mở Context Menu (chuột phải)...")
    page.keyboard.press("Escape")
    page.evaluate("""() => {
        if (typeof window.contextMenuHide === 'function') window.contextMenuHide();
        window.jQuery('#context-menu').hide().html('');
    }""")
    time.sleep(0.5)

    target_cell = page.locator("table.issues tbody tr.context-menu-selection td.checkbox, table.issues tbody tr.issue td.checkbox").first
    target_cell.scroll_into_view_if_needed()

    with page.expect_response(lambda r: "context_menu" in r.url, timeout=15000):
        try:
            target_cell.click(button='right', force=True, timeout=3000)
        except Exception:
            page.evaluate("""() => {
                const cell = document.querySelector('table.issues tbody tr.context-menu-selection td.checkbox') ||
                             document.querySelector('table.issues tbody tr.issue td.checkbox');
                if (cell) {
                    cell.dispatchEvent(new MouseEvent('contextmenu', {
                        bubbles: true, cancelable: true, view: window, button: 2, clientX: 250, clientY: 250
                    }));
                }
            }""")

    page.wait_for_selector('#context-menu', state='visible', timeout=8000)
    print("  [✓] Context Menu đã mở và nạp dữ liệu xong.")


def verify_field_applied_sample(
    page: Page,
    field_label: str,
    keyword: str,
    sample_task_id: str | None = None
) -> bool:
    """
    Xác thực thực tế trên dữ liệu xem Target Milestone hoặc Sprint đã được ghi nhận vào LIS chưa.
    Sử dụng chính xác Task ID cuối cùng được lưu trước khi reload để không phải cuộn lại từ đầu.
    """
    # 1. Kiểm tra Flash message thành công của Easy Redmine
    try:
        flash_notice = page.locator(".flash.notice, #flash_notice")
        if flash_notice.count() > 0 and flash_notice.first.is_visible():
            return True
    except Exception:
        pass

    # 2. Xác định Task ID cần kiểm tra (ưu tiên sample_task_id đã lưu trước đó)
    target_id = sample_task_id
    if not target_id:
        try:
            sample_row = page.locator("table.issues tbody tr input[type='checkbox']").last
            if sample_row.count() > 0:
                target_id = sample_row.get_attribute("value")
        except Exception:
            pass

    if not target_id:
        return False

    # 3. Kiểm tra dữ liệu thực tế của task qua API hoặc HTML
    try:
        # Kiểm tra Target Milestone qua API JSON siêu tốc (0.1s)
        if "milestone" in field_label.lower():
            api_url = f"{config.LIS_HOME_URL.rstrip('/')}/issues/{target_id}.json"
            res = page.request.get(api_url)
            if res.status == 200:
                data = res.json().get("issue", {})
                fv = data.get("fixed_version", {})
                fv_name = fv.get("name", "") if isinstance(fv, dict) else str(fv or "")
                if keyword.lower() in fv_name.lower():
                    return True
        else:
            # Kiểm tra Sprint qua trang HTML chi tiết của task (0.2s)
            task_url = f"{config.LIS_HOME_URL.rstrip('/')}/issues/{target_id}"
            res = page.request.get(task_url)
            if res.status == 200 and keyword.lower() in res.text().lower():
                return True
    except Exception:
        pass

    return False


def update_context_menu_autocomplete(
    page: Page,
    input_id: str,
    field_label: str,
    keyword: str,
    task_count: int | None = None,
    sample_task_id: str | None = None
) -> bool:
    """
    Tìm kiếm và gán giá trị autocomplete trong Context Menu,
    sau đó tự động theo dõi chu trình lưu dữ liệu và nạp lại trang:
      - Đặt marker theo dõi reload và lắng nghe sự kiện AJAX.
      - Kích hoạt select qua autocompleteselect.
      - Tự động phát hiện khi máy chủ lưu xong (qua reload hoặc ajaxComplete/ajaxError).
      - Nếu máy chủ lưu xong nhưng trình duyệt không tự reload (do timeout gateway hoặc mạng),
        chủ động gọi page.reload() để tiếp tục ngay, tránh bị treo vô tận.
      - Xác thực trực tiếp trên dữ liệu mẫu của task trước khi kết luận hoàn tất.
      - Đảm bảo bảng danh sách công việc hiển thị đầy đủ trước khi chuyển bước tiếp theo.
    """
    print(f"\n[*] Đang thiết lập {field_label}: '{keyword}'...")
    page.wait_for_selector(f"#{input_id}", state="attached", timeout=8000)

    # Đặt marker trên window cũ và cài đặt listener bắt sự kiện AJAX
    page.evaluate("""() => {
        window.__phase2_waiting_reload__ = true;
        window.__phase2_ajax_status__ = 'pending';
        window.__phase2_ajax_code__ = 0;
        if (window.jQuery) {
            window.jQuery(document).one('ajaxComplete', function(e, xhr, settings) {
                if (settings && settings.url && settings.url.includes('bulk_update')) {
                    window.__phase2_ajax_status__ = 'completed';
                    window.__phase2_ajax_code__ = xhr.status;
                }
            });
            window.jQuery(document).one('ajaxError', function(e, xhr, settings) {
                if (settings && settings.url && settings.url.includes('bulk_update')) {
                    window.__phase2_ajax_status__ = 'error';
                    window.__phase2_ajax_code__ = xhr.status;
                }
            });
        }
    }""")

    # Kích hoạt lựa chọn mục tương ứng trong Context Menu
    select_res = page.evaluate(f"""() => {{
        const inp = document.getElementById('{input_id}');
        if (!inp) return {{ error: 'Input not found: {input_id}' }};
        const jEl = window.jQuery(inp);
        const auto = jEl.data('ui-autocomplete') || jEl.data('autocomplete');
        if (!auto) return {{ error: 'No autocomplete instance found on {input_id}' }};
        const source = auto.options.source;
        const matched = source.find(x => x.label && x.label.toLowerCase().includes('{keyword.lower()}'));
        if (!matched) return {{ error: 'Not found in source: {keyword}', total: source.length }};
        
        matched.value = matched.label;
        const ret = auto.options.select.call(inp, {{ type: 'autocompleteselect' }}, {{ item: matched }});
        return {{ success: true, matched: matched, ret: ret }};
    }}""")

    if "error" in select_res:
        raise RuntimeError(select_res["error"])

    print("  [*] Đang gửi yêu cầu và chờ hệ thống LIS lưu dữ liệu...")

    t0 = time.time()
    reload_started = False
    ajax_done_time = None

    # Chờ động kết hợp bắt sự kiện AJAX và chủ động làm mới trang
    while True:
        time.sleep(1)
        elapsed = int(time.time() - t0)

        # 1. Kiểm tra xem trang cũ đã bắt đầu reload hay chưa
        try:
            has_reloaded = page.evaluate("() => window.__phase2_waiting_reload__ === undefined")
            if has_reloaded:
                reload_started = True
        except Exception:
            # Context JavaScript bị ngắt trong lúc trang đang unload/reload
            reload_started = True

        # 2. Kiểm tra trạng thái AJAX của bulk_update
        if not reload_started:
            try:
                ajax_info = page.evaluate("""() => {
                    const status = window.__phase2_ajax_status__ || 'pending';
                    const active = (window.jQuery && typeof window.jQuery.active === 'number') ? window.jQuery.active : 0;
                    const el = document.getElementById('ajax-indicator');
                    const indicatorHidden = !el || el.style.display === 'none' || window.getComputedStyle(el).display === 'none';
                    return { status: status, active: active, indicatorHidden: indicatorHidden };
                }""")
            except Exception:
                ajax_info = {"status": "pending", "active": 0, "indicatorHidden": False}

            # Nếu AJAX đã hoàn thành/lỗi, hoặc indicator đã tắt và không còn active request (sau ít nhất 30s)
            if ajax_info.get("status") in ("completed", "error") or (elapsed >= 30 and ajax_info.get("indicatorHidden") and ajax_info.get("active") == 0):
                if ajax_done_time is None:
                    ajax_done_time = time.time()

                # Nếu sau 4 giây kể từ khi AJAX xong mà trang vẫn chưa tự reload
                if time.time() - ajax_done_time >= 4:
                    print(f"  [*] Máy chủ LIS đã xử lý xong yêu cầu lưu (sau {elapsed}s). Đang làm mới danh sách công việc...")
                    try:
                        page.reload()
                        reload_started = True
                    except Exception:
                        reload_started = True

        # 3. Fallback: Nếu sau mỗi 30s kể từ mốc 90s mà vẫn chưa reload (chống đơ mạng / gateway drop)
        if not reload_started and elapsed >= 90 and elapsed % 30 == 0:
            print(f"  [*] Đang kiểm tra và cập nhật trạng thái từ máy chủ LIS ({elapsed}s)...")
            try:
                page.reload()
                reload_started = True
            except Exception:
                reload_started = True

        # 4. Khi trang đã reload, đợi bảng hiển thị đầy đủ và xác thực dữ liệu thực tế
        if reload_started:
            try:
                is_ajax_busy = page.evaluate("""() => {
                    const el = document.getElementById('ajax-indicator');
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return el.style.display !== 'none' && style.display !== 'none';
                }""")
            except Exception:
                is_ajax_busy = True

            if not is_ajax_busy:
                try:
                    rows = page.locator("table.issues tbody tr.issue, table.list.issues tbody tr").count()
                    if rows > 0:
                        # Xác thực trực tiếp trên dữ liệu mẫu của task cuối cùng
                        if verify_field_applied_sample(page, field_label, keyword, sample_task_id=sample_task_id):
                            total_display = task_count or rows
                            print(f"  [✓] Hệ thống đã xác thực lưu thành công {field_label} trên LIS ({total_display} tasks) sau {elapsed}s!")
                            break
                        else:
                            # Bảng đã nạp nhưng dữ liệu task cuối vẫn chưa đổi -> LIS vẫn đang tiếp tục ghi ngầm
                            reload_started = False
                except Exception:
                    pass

        # In log tiến độ mỗi 10 giây để người dùng theo dõi
        if elapsed > 0 and elapsed % 10 == 0 and not reload_started:
            print(f"  [*] Đang chờ máy chủ LIS lưu {field_label} vào cơ sở dữ liệu ({elapsed}s)...")

    # Đợi ổn định hoàn toàn cả DOM và Network
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass

    time.sleep(1)
    print(f"  [✓] Hoàn tất cập nhật {field_label}: '{keyword}'!")
    return True



def filter_and_assign_sprint_milestone(
    page: Page,
    proj_id: str,
    sprint_name: str,
    start_date: str,
    due_date: str,
    proj_name_keyword: str = "MAX",
    exclude_proj_name: str | None = "EGG"
) -> bool:
    """
    Điều phối trọn vẹn quy trình Giai đoạn 2 (Phase 2):
      1. Điều hướng đến trang Tasks (/issues?id={proj_id}&set_filter=0).
      2. Mở vùng bộ lọc Filters.
      3. Thêm bộ lọc 'Start date' và 'Due date'.
      4. Điền dải ngày cho Start date và Due date.
      5. Xóa tag dự án loại trừ / không khớp.
      6. Tìm kiếm và chọn dự án mục tiêu (proj_name_keyword).
      7. Áp dụng bộ lọc (Apply settings).
      8. Cuộn nạp tất cả tasks và chọn tất cả.
      9. Mở Context Menu và gán Target Milestone.
      10. Cuộn lại và chọn tất cả tasks lần 2.
      11. Mở Context Menu và gán Sprint.
    """
    print("=" * 65)
    print("🚀 BẮT ĐẦU THỰC THI GIAI ĐOẠN 2 (PHASE 2 - SPRINT & MILESTONE)")
    print("=" * 65)

    tasks_url = f"{config.LIS_HOME_URL.rstrip('/')}/issues?id={proj_id}&set_filter=0"
    print(f"\n[*] [Bước 1] Mở trang danh sách tasks: {tasks_url}...")
    safe_goto(page, tasks_url)
    page.wait_for_load_state("networkidle")

    # Mở Filters
    print("\n[*] [Bước 2] Mở Filters...")
    add_filter_select = page.locator("#add_filter_select")
    if not (add_filter_select.count() > 0 and add_filter_select.first.is_visible()):
        filters_btn = page.locator(
            "#easy-query-toggle-button-filters a, "
            "#easy-query-toggle-button-filters, "
            "div.filters a:has-text('Filters')"
        ).first
        if filters_btn.count() > 0:
            try:
                filters_btn.click()
            except Exception:
                filters_btn.click(force=True)
        time.sleep(1)

    # Thêm bộ lọc Start date và Due date
    print("\n[*] [Bước 3 & 4] Thêm bộ lọc 'Start date' và 'Due date'...")
    add_filter_select = page.locator("#add_filter_select")
    try:
        add_filter_select.select_option(value="start_date")
    except Exception:
        pass
    time.sleep(0.5)
    try:
        add_filter_select.select_option(value="due_date")
    except Exception:
        pass
    time.sleep(0.5)

    # Điền dải ngày
    print(f"\n[*] [Bước 5 & 6] Điền ngày: Start={start_date}, Due={due_date}...")
    fill_date_filter_range(page, "start_date", start_date)
    fill_date_filter_range(page, "due_date", due_date)

    # Xóa các tag dự án mặc định không khớp khỏi bộ lọc
    print(f"\n[*] [Bước 7] Dọn dẹp các thẻ dự án khác khỏi bộ lọc...")
    page.evaluate(f"""() => {{
        const delBtns = document.querySelectorAll("#values_project_id_entity_array .icon-del");
        delBtns.forEach(btn => {{
            const tagText = btn.parentElement ? btn.parentElement.innerText.trim() : '';
            if (!tagText.includes('{proj_name_keyword}')) {{
                btn.click();
            }}
        }});
    }}""")
    time.sleep(1)

    # Chọn dự án mục tiêu (nếu chưa có trong entity array)
    already_selected = page.evaluate(f"""() => {{
        const container = document.getElementById("values_project_id_entity_array");
        return container ? container.innerText.includes('{proj_name_keyword}') : false;
    }}""")

    if not already_selected:
        print(f"\n[*] [Bước 8] Chọn dự án '{proj_name_keyword}' trong bộ lọc...")
        # 1. Thử add trực tiếp qua entityArray nếu có
        added_via_js = page.evaluate(f"""() => {{
            try {{
                const el = (window.jQuery || window.$)('#values_project_id_entity_array');
                if (el && typeof el.entityArray === 'function') {{
                    el.entityArray("add", {{ id: '{proj_id}', name: '------ {proj_name_keyword}' }});
                    return true;
                }}
            }} catch(e) {{}}
            return false;
        }}""")

        if not added_via_js:
            proj_input = page.locator("#values_project_id_autocomplete")
            proj_input.wait_for(state="visible", timeout=5000)
            proj_input.click()
            proj_input.fill(f"------ {proj_name_keyword}")
            time.sleep(1)

            matched_item = page.locator(f"ul.ui-autocomplete:visible li:has-text('{proj_name_keyword}')").first
            if matched_item.count() > 0:
                matched_item.click()
                time.sleep(0.5)

    # Áp dụng bộ lọc
    print("\n[*] [Bước 9] Nhấp 'Apply settings'...")
    apply_btn = page.locator("a.apply-link.button-positive, a[onclick*='applyEasyQueryFilters']").first
    apply_btn.click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    print("  -> [✓] Đã áp dụng bộ lọc thành công!")

    # Bước 10: Target Milestone
    print("\n" + "=" * 65)
    print("🎯 BƯỚC 10: THIẾT LẬP TARGET MILESTONE")
    print("=" * 65)
    total_loaded_1 = scroll_and_load_all_tasks(page)
    if total_loaded_1 == 0:
        print("\n[!] CẢNH BÁO: Bảng không có công việc nào (0/0 tasks) thỏa mãn bộ lọc:")
        print(f"    - Ngày bắt đầu (Start Date): {start_date}")
        print(f"    - Ngày kết thúc (Due Date):  {due_date}")
        print(f"    - Dự án: {proj_name_keyword} (#{proj_id})")
        print("    Vui lòng kiểm tra lại tham số ngày/dự án trên Jenkins hoặc danh sách tasks trên LIS!")
        return False

    select_all_tasks_context_menu(page)
    # Lấy Task ID cuối cùng thực tế từ DOM (trước khi reload) để xác thực chính xác 100%
    last_cb_1 = page.locator("table.issues tbody tr input[type='checkbox']").last
    last_task_id_1 = last_cb_1.get_attribute("value") if last_cb_1.count() > 0 else None

    open_context_menu_safe(page)
    update_context_menu_autocomplete(
        page,
        input_id="fixed_version_for_context_menu_issue_autocomplete",
        field_label="Target Milestone",
        keyword=sprint_name,
        task_count=total_loaded_1,
        sample_task_id=last_task_id_1
    )

    # Bước 11: Sprint
    print("\n" + "=" * 65)
    print("🏃 BƯỚC 11: THIẾT LẬP SPRINT")
    print("=" * 65)
    total_loaded_2 = scroll_and_load_all_tasks(page)
    if total_loaded_2 == 0:
        print("\n[!] CẢNH BÁO: Bảng không có công việc nào (0 tasks) để gán Sprint.")
        return False

    select_all_tasks_context_menu(page)
    # Lấy Task ID cuối cùng thực tế từ DOM cho Bước 11
    last_cb_2 = page.locator("table.issues tbody tr input[type='checkbox']").last
    last_task_id_2 = last_cb_2.get_attribute("value") if last_cb_2.count() > 0 else None

    open_context_menu_safe(page)
    update_context_menu_autocomplete(
        page,
        input_id="easy_sprint_id_for_context_menu_issue_autocomplete",
        field_label="Sprint",
        keyword=sprint_name,
        task_count=total_loaded_2,
        sample_task_id=last_task_id_2
    )

    print("\n🎉 HOÀN THÀNH TOÀN BỘ GIAI ĐOẠN 2 THÀNH CÔNG!")
    return True

