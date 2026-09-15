# Tự Động Hóa LIS & Importer trên Jenkins CI/CD

Dự án tự động hóa toàn diện 2 giai đoạn (Phase 1 & Phase 2) cho quy trình quản lý Sprint trên hệ thống **LIS (Easy Redmine)** và **Importer (AngularJS)**, được thiết kế để vận hành tự động 100% trên hệ thống **Jenkins CI/CD (Pipeline with Parameters)**.

---

## Kiến Trúc 2 Giai Đoạn (Two-Phase Pipeline)

| Giai đoạn | Entrypoint Script | Pipeline Jenkins | Mục tiêu thực thi |
| :--- | :--- | :--- | :--- |
| **Giai đoạn 1 (Phase 1)** | `main.py` | `Jenkinsfile` | Tạo Milestone, Sprint, Parent Task trên LIS & Import 2 tầng Subtasks trên Importer |
| **Giai đoạn 2 (Phase 2)** | `main_phase2.py` | `Jenkinsfile_Phase2` | Lọc tasks theo ngày & dự án, gán hàng loạt **Target Milestone** và **Sprint** qua Context Menu |

---

## Cấu Trúc Thư Mục

```
Automation-LIS/
├── Jenkinsfile                 # Pipeline Jenkins Giai đoạn 1 (Phase 1)
├── Jenkinsfile_Phase2          # Pipeline Jenkins Giai đoạn 2 (Phase 2)
├── main.py                     # Điều phối luồng Giai đoạn 1 (Phase 1 Orchestrator)
├── main_phase2.py              # Điều phối luồng Giai đoạn 2 (Phase 2 Orchestrator)
├── lis_service.py              # Thao tác LIS: Form, Filters, Infinite Scroll, Context Menu, Bulk Update
├── importer_service.py         # Thao tác Importer: Upload 2 tầng, kiểm tra kết quả, retry và báo cáo
├── utils.py                    # Tiện ích chung (safe_goto, safe_input, check_form_error, format helpers)
├── login.py                    # Dịch vụ xác thực đăng nhập LIS & quản lý phiên auth.json (chmod 600)
├── config.py                   # Quản lý cấu hình tập trung, URLs & tự động nhận diện chế độ CI Headless
├── data_loader.py              # Nạp dữ liệu từ file/biến môi trường Jenkins & kiểm tra tính hợp lệ
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .gitignore                  # Bỏ qua file nhạy cảm & virtualenv
├── HowTo_Automation_LIS_Sprint.md    # Tài liệu kỹ thuật chi tiết (Tiếng Việt)
├── HowTo_Automation_LIS_Sprint_EN.md # Tài liệu kỹ thuật chi tiết (English)
└── README.md                   # Hướng dẫn tổng quan & vận hành
```

---

## Điểm Nổi Bật & Cải Tiến Kỹ Thuật

### Giai đoạn 1 (Phase 1 - Khởi tạo & Import)
* **Điều hướng trực tiếp:** Mở thẳng `https://lis.larion.com/projects/{PROJECT_ID}`, tự động thích ứng với mọi dự án (Team MAX: `786`, Team MSS, ...).
* **Bảo mật thông tin:** Mật khẩu LIS sử dụng kiểu `password` ẩn ký tự trên Jenkins. Tự động dọn dẹp `auth.json` và file tạm sau khi build kết thúc.
* **Tối giản hóa biểu mẫu:** Tự động sử dụng `LIS_USERNAME` làm Tác giả (Author) trên Importer.
* **Nhận file trực tiếp:** Hỗ trợ upload 2 file Excel (`.xlsx`) từ máy tính người dùng qua tham số `base64File`.
* **Cơ chế phục hồi cài đặt (Fail-Safe):** Luôn tự động khôi phục cấu hình dự án (`Planned = OFF`, `Public = ON`) khi hoàn tất hoặc ngay cả khi xảy ra lỗi đột ngột.

### Giai đoạn 2 (Phase 2 - Lọc & Gán Milestone/Sprint)
* **Tối ưu hóa `per_page=100`:** Mở trang danh sách tasks với tham số `per_page=100`, nạp ngay tối đa 100 tasks trên trang đầu tiên, giảm 80% số lần gọi mạng.
* **Kích hoạt nạp trang Native (`infinitescroll`):** Khi danh sách vượt quá 100 tasks (114, 150, 250 tasks...), script gọi trực tiếp trigger native của Easy Redmine (`.infinite-scroll-load-next-page-trigger` / `retrieve`) thay vì chỉ lăn chuột ảo, đảm bảo nạp đủ 100% dữ liệu.
* **Khử trùng lặp DOM tự động (DOM Deduplication):** Tự động loại bỏ bất kỳ dòng `<tr>` nào trùng Task ID do quá trình phân trang, đảm bảo chỉ đếm và chọn chính xác các Task ID duy nhất (`Set(task_id).size`).
* **Theo dõi lưu trữ dữ liệu thời gian thực:** Lắng nghe sự kiện AJAX (`ajaxComplete`, `ajaxError`) của Easy Redmine kết hợp cơ chế chủ động làm mới trang (`page.reload()`) ở mốc 90s+ chống nghẽn mạng gateway.
* **Xác thực dữ liệu trực tiếp trên Task cuối cùng (Last-Task Verification):**
  - Trước khi reload, script lưu chính xác Task ID cuối cùng trong danh sách.
  - **Với Target Milestone:** Gọi API ngầm `/issues/{id}.json` và kiểm tra trường `fixed_version`.
  - **Với Sprint:** Gọi trang chi tiết `/issues/{id}` và bóc tách riêng ô `<th>Sprint:</th><td>...</td>` (loại trừ ô Milestone cùng tên để chống báo hoàn tất ảo).
  - Chỉ khi task cuối cùng trong database đã đổi giá trị mới, script mới xác nhận hoàn tất.
* **Log nhịp tim (Heartbeat) mỗi 10 giây:** Cung cấp thông tin tiến độ rõ ràng trên console Jenkins (`Đang chờ máy chủ LIS lưu Target Milestone/Sprint vào cơ sở dữ liệu (10s, 20s, 30s...)`).

---

## Hướng Dẫn Thiết Lập Trên Jenkins CI/CD

### 1. Thiết Lập Job Giai Đoạn 1 (Phase 1)
1. Tạo Job mới: **New Item** -> Tên: `Automation-LIS-Sprint-Phase1` -> Kiểu **Pipeline** -> **OK**.
2. Cấu hình Pipeline:
   - **Definition**: `Pipeline script from SCM`
   - **SCM**: `Git`
   - **Repository URL**: Đường dẫn Git repository
   - **Branch Specifier**: `*/main`
   - **Script Path**: `Jenkinsfile`
3. Nhấn **Save**, sau đó nhấn **Build Now** lần đầu tiên để nạp các tham số.
4. Tải lại trang (F5) để sử dụng **Build with Parameters**:
   - `LIS_USERNAME`, `LIS_PASSWORD`: Tài khoản và mật khẩu LIS.
   - `SPRINT_NAME`: Tên Sprint (ví dụ: `2026 Oct 01 Sprint`).
   - `START_DATE`, `DUE_DATE`: Ngày bắt đầu và ngày nộp (`YYYY-MM-DD`).
   - `RELEASE_TYPE`, `ENVIRONMENT`: Loại phát hành và môi trường triển khai.
   - `ASSIGNEE`: Người phụ trách Parent Task.
   - `PROJECT_ID`: Mã dự án (mặc định: `786` cho Team MAX).
   - `STRUCTURE_FILE`, `WORK_ITEMS_FILE`: Tải lên 2 file Excel từ máy tính.
5. Nhấn **Build**.

---

### 2. Thiết Lập Job Giai Đoạn 2 (Phase 2)
1. Tạo Job mới: **New Item** -> Tên: `Automation-LIS-Sprint-Phase2` -> Kiểu **Pipeline** -> **OK**.
2. Cấu hình Pipeline:
   - **Definition**: `Pipeline script from SCM`
   - **SCM**: `Git`
   - **Repository URL**: Đường dẫn Git repository
   - **Branch Specifier**: `*/main`
   - **Script Path**: `Jenkinsfile_Phase2`
3. Nhấn **Save**, sau đó nhấn **Build Now** lần đầu tiên để nạp các tham số.
4. Tải lại trang (F5) để sử dụng **Build with Parameters**:
   - `LIS_USERNAME`, `LIS_PASSWORD`: Tài khoản và mật khẩu LIS.
   - `PROJECT_ID`: Mã dự án (mặc định: `786` cho Team MAX).
   - `SPRINT_NAME`: Tên Sprint cần gán (ví dụ: `2026 Oct 01 Sprint`).
   - `START_DATE`: Ngày bắt đầu để lọc công việc (`YYYY-MM-DD`).
   - `DUE_DATE`: Ngày kết thúc để lọc công việc (`YYYY-MM-DD`).
5. Nhấn **Build** -> Hệ thống tự động lọc tasks, nạp đủ 100% danh sách, gán Target Milestone và Sprint, đồng thời xác thực hoàn tất trên task cuối cùng.

---

## Chạy Thử Nghiệm Tại Local (Terminal)

```bash
# 1. Kích hoạt môi trường ảo
source .venv/bin/activate

# 2. Cài đặt thư viện & Playwright Chromium
pip install -r requirements.txt
playwright install chromium

# 3. Thiết lập biến môi trường chung
export LIS_USERNAME="your_username"
export LIS_PASSWORD="your_password"
export SPRINT_NAME="2026 Oct 01 Sprint"
export START_DATE="2026-10-01"
export DUE_DATE="2026-10-17"
export PROJECT_ID="786"
export HEADLESS=False

# 4. Chạy thử nghiệm Giai đoạn 1 (Phase 1)
export ASSIGNEE="Trang Pham-Tran-Minh"
python3 main.py

# 5. Chạy thử nghiệm Giai đoạn 2 (Phase 2)
python3 main_phase2.py
```
