# Tự Động Hóa LIS & Importer trên Jenkins CI/CD

Dự án tự động hóa toàn diện quy trình tạo **Milestone, Sprint, Parent Task trên LIS (Redmine)** và **Import 2 tầng Subtasks trên Importer (Larion)**, chạy tự động 100% trên hệ thống **Jenkins nội bộ công ty**.

* **Địa chỉ Jenkins công ty**: [http://172.16.4.215:8080/view/MAX.Intern/](http://172.16.4.215:8080/view/MAX.Intern/)

---

## 📁 Cấu Trúc Thư Mục Tinh Gọn (Không chứa file dữ liệu mẫu)

```
Automation-LIS/
├── Jenkinsfile                 # Cấu hình Jenkins Declarative Pipeline (Build with Parameters)
├── main.py                     # Kịch bản lõi Playwright 19 bước (Chạy ngầm Headless)
├── login.py                    # Module xác thực đăng nhập LIS an toàn
├── config.py                   # Quản lý cấu hình tập trung & nhận diện môi trường CI
├── data_loader.py              # Nạp dữ liệu & hỗ trợ ghi đè biến môi trường
├── sprint_data.json            # File cấu hình dữ liệu Sprint mặc định
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .env.example                # File mẫu biến môi trường
├── .gitignore                  # Bỏ qua file nhạy cảm & virtualenv
└── README.md                   # Hướng dẫn chi tiết
```

---

## 🌟 Hướng Dẫn Thiết Lập Trên Jenkins Công Ty (`http://172.16.4.215:8080/view/MAX.Intern/`)

### 1️⃣ Bước 1: Thêm Credentials Tài Khoản LIS vào Jenkins
*(Chỉ cần cấu hình 1 lần duy nhất)*
1. Truy cập Jenkins: `http://172.16.4.215:8080/`
2. Vào **Manage Jenkins** > **Credentials** > **System** > **Global credentials** > **Add Credentials**.
3. Điền thông tin:
   - **Kind**: `Username with password`
   - **ID**: `lis_credentials` *(bắt buộc đặt đúng ID này)*
   - **Username**: Tài khoản LIS của bạn (ví dụ: `minhvh`)
   - **Password**: Mật khẩu LIS của bạn
   - **Description**: `LIS Credentials for Automation`
4. Bấm **Create**.

---

### 2️⃣ Bước 2: Tạo Job Pipeline trên Jenkins
1. Truy cập View: **`http://172.16.4.215:8080/view/MAX.Intern/`**
2. Bấm **New Item**:
   - Nhập tên Item: ví dụ `Automation-LIS-Sprint`
   - Chọn kiểu: **Pipeline** > Bấm **OK**.
3. Trong trang cấu hình Job:
   - Kéo xuống mục **Pipeline**:
     - **Definition**: Chọn `Pipeline script from SCM`
     - **SCM**: Chọn `Git`
     - **Repository URL**: Điền đường dẫn Git repo của dự án này
     - **Credentials**: Chọn credential Git của bạn
     - **Branch Specifier**: `*/main` hoặc `*/master`
     - **Script Path**: `Jenkinsfile`
4. Bấm **Save**.

---

### 3️⃣ Bước 3: Thực Thi — Bấm "Build with Parameters"
Mỗi lần cần tạo Sprint mới:
1. Vào Job `Automation-LIS-Sprint` > Bấm **Build with Parameters**.
2. Điền thông tin Sprint:
   - **`NAME_SPRINT`**: Tên Sprint (ví dụ: `2026 Oct 01 Sprint`)
   - **`START_DATE`**: Ngày bắt đầu (`YYYY-MM-DD`, ví dụ: `2026-10-01`)
   - **`DUE_DATE`**: Ngày nộp (`YYYY-MM-DD`, ví dụ: `2026-10-17`)
   - **`RELEASE_TYPE`**: `Internal` hoặc `External`
   - **`ENVIRONMENT`**: `Development`, `Testing`, `Production`, `Local`
   - **`ASSIGNEE`**: Người phụ trách (ví dụ: `Trang Pham-Tran-Minh`)
   - **`PROJECT_ID`**: Mã dự án Importer (ví dụ: `786`)
   - **`AUTHOR`**: Tác giả Importer (ví dụ: `minhvh`)
3. **Bắt buộc tải lên 2 file Excel từ máy tính của bạn**:
   - 📁 **`STRUCTURE_FILE_UPLOAD`**: Bấm Browse... chọn file Structure Template Excel.
   - 📁 **`WORK_ITEMS_FILE_UPLOAD`**: Bấm Browse... chọn file Work Items Excel.
4. Bấm **`Build`** $\rightarrow$ Jenkins sẽ tự động tiếp nhận 2 file, chạy toàn bộ quy trình Playwright ở chế độ Headless, hoàn tất import và tự động dọn dẹp file an toàn!
