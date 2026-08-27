import os
from playwright.sync_api import sync_playwright
import config


def login_and_save_session(username: str | None = None, password: str | None = None) -> bool:
    """Đăng nhập LIS và lưu phiên (cookies) vào auth.json."""
    username = username or config.LIS_USERNAME
    password = password or config.LIS_PASSWORD

    if not username or not password:
        print("[LỖI] Vui lòng cấu hình LIS_USERNAME và LIS_PASSWORD trong file .env hoặc truyền trực tiếp.")
        return False

    print(f"[*] Đang khởi động trình duyệt (Headless={config.HEADLESS})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"[*] Đang truy cập trang đăng nhập: {config.LIS_HOME_URL}")
        for attempt in range(1, 6):
            try:
                page.goto(config.LIS_HOME_URL, timeout=60000, wait_until="load")
                break
            except Exception as e:
                print(f"[!] Cảnh báo mạng khi truy cập login (Lần {attempt}/5): {e}")
                if attempt == 5:
                    raise
                import time
                time.sleep(2 * attempt)

        # Điền form đăng nhập
        print("[*] Đang điền thông tin đăng nhập...")
        page.locator("#username").fill(username)
        page.locator("#password").fill(password)

        # Tích chọn Stay logged in nếu có
        autologin_checkbox = page.locator("#autologin")
        try:
            if autologin_checkbox.is_visible(timeout=3000):
                autologin_checkbox.check()
        except Exception:
            pass

        # Bấm nút Login
        print("[*] Đang gửi yêu cầu đăng nhập...")
        page.locator("button[name='login']").click()

        # Đợi trang chuyển hướng hoặc tải xong
        page.wait_for_load_state("networkidle")

        # Kiểm tra thông báo lỗi (thường là flash error trong Redmine/LIS)
        error_flash = page.locator("#flash_error, .flash.error")
        if error_flash.count() > 0 and error_flash.first.is_visible():
            print(f"[X] Đăng nhập thất bại: {error_flash.first.inner_text().strip()}")
            browser.close()
            return False

        print(f"[✓] Đăng nhập thành công! Tiêu đề trang hiện tại: {page.title()}")
        print(f"[✓] URL hiện tại: {page.url}")

        # Lưu lại phiên đăng nhập (Cookies, Local Storage)
        context.storage_state(path=str(config.AUTH_FILE))

        # Giới hạn quyền truy cập file session (chỉ owner đọc/ghi)
        try:
            os.chmod(config.AUTH_FILE, 0o600)
        except OSError:
            pass

        print(f"[✓] Đã lưu phiên đăng nhập vào: {config.AUTH_FILE}")

        browser.close()
        return True


if __name__ == "__main__":
    login_and_save_session()
