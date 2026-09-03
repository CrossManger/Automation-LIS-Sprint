# Tự Động Hóa LIS & Importer trên Jenkins CI/CD

Dự án tự động hóa toàn diện quy trình tạo **Milestone, Sprint, Parent Task trên LIS** và **Import 2 tầng Subtasks trên Importer**, được thiết kế để chạy tự động 100% trên hệ thống **Jenkins CI/CD (Pipeline with Parameters)**.

---

## Cấu Trúc Thư Mục

```
Automation-LIS/
├── Jenkinsfile                 # Cấu hình Jenkins Declarative Pipeline (Build with Parameters)
├── main.py                     # Kịch bản lõi Playwright tự động hóa (Chạy ngầm Headless)
├── login.py                    # Module xác thực đăng nhập LIS an toàn
├── config.py                   # Quản lý cấu hình tập trung & nhận diện môi trường CI
├── data_loader.py              # Nạp dữ liệu & hỗ trợ ghi đè biến môi trường
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .gitignore                  # Bỏ qua file nhạy cảm & virtualenv
└── README.md                   # Hướng dẫn chi tiết
```

---

## Điểm Nổi Bật & Tính Năng Mới

* **Điều hướng dự án trực tiếp:** Truy cập thẳng `https://lis.larion.com/projects/{PROJECT_ID}`, không cần thao tác tìm kiếm hay chọn menu gợi ý, tự động tương thích với mọi dự án (Team MAX: `786`, Team MSS, ...).
* **Bảo mật mật khẩu:** Tham số `LIS_PASSWORD` sử dụng kiểu `password` che ký tự khi nhập trên Jenkins.
* **Tối giản hóa biểu mẫu:** Tự động sử dụng `LIS_USERNAME` làm Tác giả (Author) trên Importer, không yêu cầu nhập trường Author riêng biệt.
* **Nhận file trực tiếp từ trình duyệt:** Người dùng chọn file Excel từ máy tính cá nhân qua tham số `base64File`, hệ thống tự động chuẩn hóa định dạng `.xlsx`.
* **Cơ chế phục hồi cài đặt (Fail-Safe):** Luôn tự động khôi phục cấu hình dự án (`Planned = OFF`, `Public = ON`) khi hoàn tất hoặc ngay cả khi xảy ra lỗi đột ngột.

---

## Hướng Dẫn Thiết Lập Trên Jenkins CI/CD

### Bước 1: Tạo Job Pipeline trên Jenkins
1. Truy cập vào trang quản lý Jenkins.
2. Chọn **New Item**:
   - Nhập tên Job (ví dụ: `Automation-LIS-Sprint`)
   - Chọn kiểu: **Pipeline** -> Chọn **OK**.
3. Trong trang cấu hình Job:
   - Di chuyển đến mục **Pipeline**:
     - **Definition**: Chọn `Pipeline script from SCM`
     - **SCM**: Chọn `Git`
     - **Repository URL**: Điền đường dẫn Git repository của dự án
     - **Credentials**: Chọn credential Git (nếu repository ở chế độ Private)
     - **Branch Specifier**: `*/main` hoặc `*/master`
     - **Script Path**: `Jenkinsfile`
4. Chọn **Save**.

---

### Bước 2: Khởi Tạo Lần Đầu
1. Nhấn nút **Build Now** một lần đầu tiên để Jenkins nạp toàn bộ tham số từ `Jenkinsfile`.
2. Tải lại trang (F5). Nút `Build Now` bên menu trái sẽ tự động chuyển thành **Build with Parameters**.

---

### Bước 3: Thực Thi với "Build with Parameters"
Mỗi khi cần tạo Sprint mới:
1. Truy cập Job -> Chọn **Build with Parameters**.
2. Điền thông tin vào biểu mẫu:
   - **`LIS_USERNAME`**: Tài khoản LIS *(Bắt buộc)*
   - **`LIS_PASSWORD`**: Mật khẩu LIS *(Bắt buộc - Ký tự được che)*
   - **`SPRINT_NAME`**: Tên Sprint (ví dụ: `2026 Oct 01 Sprint`) *(Bắt buộc)*
   - **`START_DATE`**: Ngày bắt đầu (`YYYY-MM-DD`, ví dụ: `2026-10-01`) *(Bắt buộc)*
   - **`DUE_DATE`**: Ngày nộp (`YYYY-MM-DD`, ví dụ: `2026-10-17`) *(Bắt buộc)*
   - **`RELEASE_TYPE`**: Chọn `Internal` hoặc `External`
   - **`ENVIRONMENT`**: Chọn `Development`, `Testing`, `Production`, hoặc `Local`
   - **`ASSIGNEE`**: Người phụ trách Parent Task (ví dụ: `Trang Pham-Tran-Minh`) *(Bắt buộc)*
   - **`PROJECT_ID`**: Mã ID dự án trên LIS & Importer (ví dụ: `786` cho Team MAX hoặc mã ID của team khác) *(Bắt buộc)*
3. **Tải lên 2 file Excel từ máy tính**:
   - **`STRUCTURE_FILE`**: Chọn file Cấu trúc Sprint (Tầng 1).
   - **`WORK_ITEMS_FILE`**: Chọn file Chi tiết Work Items (Tầng 2).
4. Nhấn **Build** -> Jenkins sẽ tự động chạy toàn bộ quy trình Playwright ở chế độ Headless, in log chi tiết và tự động dọn dẹp môi trường sau khi hoàn tất.

---

## Chạy Thử Nghiệm Tại Local (Terminal)

Nếu cần chạy thử nghiệm trực tiếp trên môi trường máy cá nhân:

```bash
# 1. Kích hoạt môi trường ảo
source .venv/bin/activate

# 2. Cài đặt thư viện & Playwright Chromium
pip install -r requirements.txt
playwright install chromium

# 3. Thiết lập biến môi trường và chạy
export LIS_USERNAME="your_username"
export LIS_PASSWORD="your_password"
export SPRINT_NAME="2026 Oct 01 Sprint"
export START_DATE="2026-10-01"
export DUE_DATE="2026-10-17"
export ASSIGNEE="Trang Pham-Tran-Minh"
export PROJECT_ID="786"
export HEADLESS=False

python3 main.py
```
