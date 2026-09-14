import re
import sys
import time
from playwright.sync_api import Page, Locator
import config


def get_sprint_name(item: dict) -> str:
    """Lấy tên sprint/milestone từ dữ liệu JSON (hỗ trợ cả key cũ và mới)."""
    return item.get("Name Sprint") or item.get("Name", "Sprint mới")


def safe_goto(page_obj: Page, url: str, max_retries: int = 6, timeout: int = 60000):
    """Truy cập URL an toàn với cơ chế tự động thử lại tối đa 6 lần khi gặp sự cố mạng (ERR_NETWORK_CHANGED, timeout, v.v.)."""
    for attempt in range(1, max_retries + 1):
        try:
            return page_obj.goto(url, timeout=timeout, wait_until="load")
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


def select_option_with_fallback(locator: Locator, label: str, field_name: str) -> bool:
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


def safe_input(prompt: str, default: str = "") -> str:
    """Gọi input() an toàn — trả về default nếu headless hoặc không có stdin."""
    if config.HEADLESS or not sys.stdin.isatty():
        return default
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return default
