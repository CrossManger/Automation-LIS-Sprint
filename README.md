# Tự Động Hóa LIS & Importer trên Jenkins CI/CD

Dự án tự động hóa toàn diện quy trình tạo **Milestone, Sprint, Parent Task trên LIS** và **Import 2 tầng Subtasks trên Importer**, được thiết kế để chạy tự động 100% trên hệ thống **Jenkins CI/CD (Pipeline with Parameters)**.

---

## 📁 Cấu Trúc Thư Mục Tinh Gọn

```
Automation-LIS/
├── Jenkinsfile                 # Cấu hình Jenkins Declarative Pipeline (Build with Parameters)
├── main.py                     # Kịch bản lõi Playwright 19 bước (Chạy ngầm Headless)
├── login.py                    # Module xác thực đăng nhập LIS an toàn
├── config.py                   # Quản lý cấu hình tập trung & nhận diện môi trường CI
├── data_loader.py              # Nạp dữ liệu & hỗ trợ ghi đè biến môi trường
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .gitignore                  # Bỏ qua file nhạy cảm & virtualenv
└── README.md                   # Hướng dẫn chi tiết
```

---

## 🌟 Hướng Dẫn Thiết Lập Trên Jenkins CI/CD

### 1️⃣ Bước 1: Tạo Job Pipeline trên Jenkins
1. Truy cập vào trang quản lý Jenkins của bạn.
2. Bấm **New Item** *(Tạo mục mới)*:
   - Nhập tên Job (ví dụ: `Automation-LIS-Sprint`)
   - Chọn kiểu: **Pipeline** $\rightarrow$ Bấm **OK**.
3. Trong trang cấu hình Job:
   - Kéo xuống mục **Pipeline**:
     - **Definition**: Chọn `Pipeline script from SCM`
     - **SCM**: Chọn `Git`
     - **Repository URL**: Điền đường dẫn Git repo của dự án
     - **Credentials**: Chọn credential Git (nếu repo ở chế độ Private)
     - **Branch Specifier**: `*/main` hoặc `*/master`
     - **Script Path**: `Jenkinsfile`
4. Bấm **Save**.

---

### 2️⃣ Bước 2: Khởi Tạo Lần Đầu
1. Bấm nút **Build Now** 1 lần đầu tiên để Jenkins nạp cấu hình từ `Jenkinsfile`.
2. Bấm **F5 (Refresh trang)**. Nút `Build Now` bên menu trái sẽ tự động chuyển thành **`Build with Parameters`**.

---

### 3️⃣ Bước 3: Thực Thi — Bấm "Build with Parameters"
Mỗi lần cần tạo Sprint mới:
1. Vào Job $\rightarrow$ Bấm **`Build with Parameters`**.
2. Điền thông tin vào form:
   - 👤 **`LIS_USERNAME`**: Tài khoản LIS của bạn *(Bắt buộc)*
   - 🔒 **`LIS_PASSWORD`**: Mật khẩu LIS của bạn *(Bắt buộc - Tự động che dấu sao `••••••••`)*
   - **`NAME_SPRINT`**: Tên Sprint (ví dụ: `2026 Oct 01 Sprint`)
   - **`START_DATE`**: Ngày bắt đầu (`YYYY-MM-DD`, ví dụ: `2026-10-01`)
   - **`DUE_DATE`**: Ngày nộp (`YYYY-MM-DD`, ví dụ: `2026-10-17`)
   - **`RELEASE_TYPE`**: Chọn `Internal` hoặc `External`
   - **`ENVIRONMENT`**: Chọn `Development`, `Testing`, `Production`, `Local`
   - **`ASSIGNEE`**: Tên người được giao task
   - **`PROJECT_ID`**: Mã ID dự án trên Importer
   - **`AUTHOR`**: Tên tác giả Importer
3. **Tải lên 2 file Excel từ máy tính cá nhân**:
   - 📁 **`STRUCTURE_FILE_UPLOAD`**: Bấm Browse chọn file Excel Structure Template.
   - 📁 **`WORK_ITEMS_FILE_UPLOAD`**: Bấm Browse chọn file Excel chi tiết Work Items.
4. Bấm nút **`Build`** $\rightarrow$ Jenkins sẽ tự động chạy toàn bộ quy trình Playwright ở chế độ Headless, in log chi tiết và tự động dọn dẹp file an toàn sau khi hoàn tất.

---

## 💻 Chạy Thử Nghiệm Thủ Công Tại Local (Terminal)

Nếu bạn muốn chạy thử nghiệm trên máy cá nhân trước khi kích hoạt trên Jenkins:

```bash
# 1. Kích hoạt môi trường ảo
source .venv/bin/activate

# 2. Cài đặt thư viện & Playwright Chromium (nếu chưa cài)
pip install -r requirements.txt
playwright install chromium

# 3. Thiết lập thông tin đăng nhập và chạy
export LIS_USERNAME="your_username"
export LIS_PASSWORD="your_password"
export HEADLESS=False

python main.py sprint_data.json
```
