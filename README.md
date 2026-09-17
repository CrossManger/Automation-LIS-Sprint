# Tự Động Hóa LIS & Importer trên Jenkins CI/CD

Dự án tự động hóa toàn diện quy trình quản lý Sprint trên hệ thống **LIS (Easy Redmine)** và **Importer (AngularJS)**, được vận hành tập trung trên **một Job duy nhất trên Jenkins CI/CD (Unified Pipeline with Parameters)**.

Hệ thống hỗ trợ thực thi linh hoạt: chạy trọn gói từ đầu đến cuối (**Full process**) hoặc chạy riêng biệt từng giai đoạn (**Phase 1** / **Phase 2**) tùy theo nhu cầu vận hành.

---

## Kiến Trúc Pipeline Hợp Nhất (Unified Single-Job Pipeline)

Thay vì phải tạo và cấu hình 2 Job riêng biệt, toàn bộ tiến trình hiện được tích hợp trong **một file `Jenkinsfile` duy nhất**:

| Chế độ (`REQUEST_TYPE`) | Giai đoạn thực thi | Mô tả chi tiết |
| :--- | :--- | :--- |
| **`Full process (1 + 2)`** *(Mặc định)* | Phase 1 + Phase 2 | Tự động hóa toàn trình: Tạo Milestone, Sprint, Parent Task, nạp 2 file Excel, sau đó tự động lọc danh sách và gán hàng loạt Target Milestone & Sprint. |
| **`(1) Create Milestone, Sprint, Parent task and import tasks`** | Chỉ Phase 1 | Dành cho đợt đầu Sprint: Tạo Milestone, Sprint, cấu hình dự án, tạo Parent Task và nạp 2 tầng Subtasks từ Excel. |
| **`(2) Assign Milestone and Sprint for the tasks created in sprint.`** | Chỉ Phase 2 | Dành cho việc cập nhật bổ sung: Lọc các tasks theo dải ngày, nạp 100% dữ liệu, gán hàng loạt Target Milestone và Sprint qua Context Menu (không cần nạp file Excel). |

---

## Cấu Trúc Thư Mục

```
Automation-LIS/
├── Jenkinsfile                 # Pipeline Jenkins hợp nhất (Hỗ trợ Full Process, Type 1, Type 2)
├── main.py                     # Điều phối luồng Giai đoạn 1 (Phase 1 Orchestrator)
├── main_phase2.py              # Điều phối luồng Giai đoạn 2 (Phase 2 Orchestrator)
├── lis_service.py              # Nghiệp vụ LIS: Forms, Filters, Infinite Scroll, Context Menu, Bulk Update
├── importer_service.py         # Nghiệp vụ Importer: Upload 2 tầng Excel, kiểm tra kết quả, retry & báo cáo
├── utils.py                    # Tiện ích chung (safe_goto, safe_input, check_form_error, retry)
├── login.py                    # Xác thực đăng nhập LIS & quản lý phiên an toàn auth.json (chmod 600)
├── config.py                   # Cấu hình tập trung, URLs & tự động nhận diện chế độ CI Headless
├── data_loader.py              # Nạp dữ liệu từ file JSON / biến môi trường Jenkins & validate
├── requirements.txt            # Danh sách thư viện Python (playwright, pandas, openpyxl, ...)
├── .gitignore                  # Bỏ qua credentials, auth.json, virtualenv & file tạm
├── HowTo_Automation_LIS_Sprint.md    # Hướng dẫn kỹ thuật chi tiết (Tiếng Việt)
├── HowTo_Automation_LIS_Sprint_EN.md # Hướng dẫn kỹ thuật chi tiết (English)
└── README.md                   # Hướng dẫn tổng quan & vận hành hệ thống
```

---

## Điểm Nổi Bật & Tính Năng Kỹ Thuật

### 1. Tự Động Nhận Diện Dự Án & Bộ Lọc (`PROJECT_ID` & `PROJECT_FILTER`)
- **Tự động ánh xạ:** Người dùng chỉ cần nhập mã dự án (`PROJECT_ID`):
  - `786` $\rightarrow$ Tự động áp dụng bộ lọc hiển thị `------ MAX` (Team MAX).
  - `83` $\rightarrow$ Tự động áp dụng bộ lọc hiển thị `---------- Dev 1`.
- **Khả năng mở rộng cho dự án bất kỳ:** Nếu `PROJECT_ID` khác 786 và 83, hệ thống yêu cầu nhập trường `PROJECT_FILTER` (ví dụ: `------ TÊN_DỰ_ÁN`) để áp dụng chính xác cho dự án đó mà không cần sửa code.
- **Loại trừ EGG triệt để từ đầu:** Toàn bộ quá trình từ thiết lập cấu hình dự án, tạo Parent Task, chọn dự án trên Importer đến bộ lọc công việc Phase 2 đều tự động loại trừ các dự án/tag chứa `EGG`.

### 2. Giai đoạn 1 (Phase 1 - Khởi tạo & Import)
* **Điều hướng trực tiếp:** Mở thẳng `https://lis.larion.com/projects/{PROJECT_ID}`, tự động thích ứng với mọi dự án.
* **Bảo mật tuyệt đối:** Mật khẩu LIS sử dụng kiểu `password` ẩn ký tự trên Jenkins. Tự động thu hồi phiên và dọn dẹp `auth.json`, file Excel sau khi build.
* **Tối giản hóa biểu mẫu:** Tự động lấy `LIS_USERNAME` làm Tác giả (Author) trên Importer.
* **Nhận file trực tiếp:** Hỗ trợ upload 2 file Excel (`.xlsx`) từ máy tính cá nhân qua `base64File`.
* **Cơ chế Fail-Safe:** Tự động hoàn trả cấu hình dự án (`Planned = OFF`, `Public = ON`) ngay cả khi xảy ra lỗi bất ngờ.

### 3. Giai đoạn 2 (Phase 2 - Lọc & Gán Hàng Loạt)
* **Tối ưu hóa `per_page=100`:** Mở trang danh sách tasks với `per_page=100`, giảm 80% số lần gọi mạng so với mặc định.
* **Kích hoạt nạp trang Native (`infinitescroll`):** Gọi trực tiếp trigger native của Easy Redmine (`.infinite-scroll-load-next-page-trigger` / `retrieve`) khi số tasks vượt quá 100, bảo đảm nạp đủ 100% dữ liệu.
* **Khử trùng lặp DOM thời gian thực (DOM Deduplication):** Loại bỏ các dòng `<tr>` trùng Task ID do quá trình phân trang của Redmine gây ra, cam kết đếm và chọn chính xác các Task ID duy nhất.
* **Xác thực dữ liệu trực tiếp trên Task cuối cùng (Last-Task DB Verification):**
  - **Target Milestone:** Kiểm tra trường `fixed_version` qua API `/issues/{id}.json`.
  - **Sprint:** Bóc tách riêng ô `<th>Sprint:</th>` của task cuối cùng (loại trừ ô Milestone cùng tên để chống báo thành công ảo).
* **Chống treo mạng Gateway Timeout:** Chủ động reload ở mốc 90s+ và theo dõi nhịp tim (Heartbeat log) mỗi 10 giây.

---

## Hướng Dẫn Vận Hành Trên Jenkins CI/CD

### 1. Tạo & Thiết Lập Job
1. Trên Jenkins, chọn **New Item** $\rightarrow$ Đặt tên: `Intern.Automation.LIS.Sprint` $\rightarrow$ Chọn kiểu **Pipeline** $\rightarrow$ Nhấn **OK**.
2. Tại mục **Pipeline**:
   - **Definition**: `Pipeline script from SCM`
   - **SCM**: `Git`
   - **Repository URL**: URL repository dự án
   - **Branch Specifier**: `*/main`
   - **Script Path**: `Jenkinsfile`
3. Nhấn **Save**, sau đó nhấn **Build Now** lần đầu tiên để Jenkins nạp các định nghĩa tham số.
4. Tải lại trang (F5) để hiển thị giao diện **Build with Parameters**.

---

### 2. Ý Nghĩa Các Tham Số (Build with Parameters)

#### Nhóm A: Lựa chọn loại yêu cầu (Request Type)
* **`REQUEST_TYPE`** (Choice):
  - `Full process (1 + 2)`: Chạy trọn gói cả 2 Phase.
  - `(1) Create Milestone, Sprint, Parent task and import tasks`: Chỉ chạy Phase 1.
  - `(2) Assign Milestone and Sprint for the tasks created in sprint.`: Chỉ chạy Phase 2.

#### Nhóm B: Dùng chung & Bắt buộc cho cả 2 Phase (hoặc khi chọn Type 2)
* **`LIS_USERNAME`**: Tài khoản LIS.
* **`LIS_PASSWORD`**: Mật khẩu LIS (ẩn ký tự).
* **`PROJECT_ID`**: Mã dự án LIS (Ví dụ: `786` cho Team MAX, `83` cho Dev 1).
* **`PROJECT_FILTER`**: Bộ lọc tên dự án (Bắt buộc nếu `PROJECT_ID` khác 786 và 83, ví dụ: `------ TÊN_DỰ_ÁN`). Nếu là 786 hoặc 83 thì có thể để trống.
* **`SPRINT_NAME`**: Tên Sprint (Ví dụ: `2026 Oct 01 Sprint`).
* **`START_DATE`**: Ngày bắt đầu Sprint (`YYYY-MM-DD`).
* **`DUE_DATE`**: Ngày kết thúc / nộp Sprint (`YYYY-MM-DD`).

#### Nhóm C: Chỉ dùng khi chạy Type (1) hoặc Full process (Bỏ qua khi chọn Type 2)
* **`ASSIGNEE`**: Người phụ trách Parent Task (Ví dụ: `Trang Pham-Tran-Minh`).
* **`RELEASE_TYPE`**: Loại phát hành (`Internal` / `External`).
* **`ENVIRONMENT`**: Môi trường triển khai (`Development`, `Production`, `Testing`, `Local`).
* **`STRUCTURE_FILE`**: Chọn file Excel Cấu trúc Sprint Tầng 1 (`structure_template.xlsx`).
* **`WORK_ITEMS_FILE`**: Chọn file Excel Chi tiết Work Items Tầng 2 (`work_items_detail.xlsx`).

---

## Chạy Thử Nghiệm Tại Local (Terminal)

```bash
# 1. Kích hoạt môi trường ảo
source .venv/bin/activate

# 2. Cài đặt thư viện phụ thuộc & Playwright Chromium
pip install -r requirements.txt
playwright install chromium

# 3. Thiết lập biến môi trường
export LIS_USERNAME="your_username"
export LIS_PASSWORD="your_password"
export SPRINT_NAME="2026 Oct 01 Sprint"
export START_DATE="2026-10-01"
export DUE_DATE="2026-10-17"
export PROJECT_ID="786"               # Hoặc "83", hoặc ID khác
# export PROJECT_FILTER="------ MAX"   # (Tùy chọn: chỉ cần nếu ID khác 786 và 83)
export HEADLESS="False"               # Mở trình duyệt có giao diện trực quan

# 4. Kiểm tra Giai đoạn 1 (Phase 1)
export ASSIGNEE="Trang Pham-Tran-Minh"
export RELEASE_TYPE="Internal"
export ENVIRONMENT="Development"
export STRUCTURE_FILE="structure_template.xlsx"
export WORK_ITEMS_FILE="work_items_detail.xlsx"
python3 main.py

# 5. Kiểm tra Giai đoạn 2 (Phase 2)
python3 main_phase2.py
```

---

## Xử Lý Sự Cố Thường Gặp (Troubleshooting)

1. **Lỗi `bad substitution` trên Jenkins:**
   - Đảm bảo trong khối `sh ''' ... '''`, tất cả cú pháp lấy giá trị mặc định của biến môi trường tuân thủ đúng chuẩn Bash: `${REQUEST_TYPE:-$EXECUTION_MODE}` (không dùng toán tử Elvis `?:` của Groovy).
2. **Lỗi thiếu file khi chọn Type (2):**
   - Pipeline đã được cấu hình tự động bỏ qua kiểm tra `STRUCTURE_FILE` và `WORK_ITEMS_FILE` khi `REQUEST_TYPE` bắt đầu bằng `(2)`.
3. **Dự án mới không tìm thấy trên bộ lọc:**
   - Điền chính xác chuỗi hiển thị dự án trong trường `PROJECT_FILTER` (bao gồm cả các dấu gạch ngang phía trước, ví dụ: `------ TÊN_DỰ_ÁN`).
