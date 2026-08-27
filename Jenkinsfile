pipeline {
    agent any

    parameters {
        string(name: 'LIS_USERNAME', defaultValue: '', description: 'LIS Username')
        string(name: 'LIS_PASSWORD', defaultValue: '', description: 'LIS Password')
        string(name: 'NAME_SPRINT', defaultValue: '', description: 'Name Sprint')
        string(name: 'START_DATE', defaultValue: '', description: 'Release Start Date (YYYY-MM-DD)')
        string(name: 'DUE_DATE', defaultValue: '', description: 'Release Submission Date (YYYY-MM-DD)')
        choice(name: 'RELEASE_TYPE', choices: ['Internal', 'External', ''], description: 'Release Type')
        choice(name: 'ENVIRONMENT', choices: ['Development', 'Testing', 'Production', 'Local'], description: 'Environment')
        string(name: 'ASSIGNEE', defaultValue: '', description: 'Assignee')
        string(name: 'PROJECT_ID', defaultValue: '', description: 'Project ID Importer (e.g. 786 for Team MAX)')
        string(name: 'AUTHOR', defaultValue: '', description: 'Author Importer')
        file(name: 'STRUCTURE_FILE_UPLOAD', description: 'Structure File (Template)')
        file(name: 'WORK_ITEMS_FILE_UPLOAD', description: 'Work Items File')
    }

    environment {
        HEADLESS = 'True'
        PYTHONUNBUFFERED = '1'
        CI = 'true'
        PATH = "$HOME/.local/bin:$PATH"
    }

    stages {
        stage('1. Kiểm Tra Tính Hợp Lệ Của Tham Số (Validate Parameters)') {
            steps {
                script {
                    echo "=========================================="
                    echo "🔍 Đang kiểm tra các thông tin nhập liệu..."
                    echo "=========================================="
                    
                    def missingParams = []
                    
                    if (!params.LIS_USERNAME?.trim()) missingParams.add("LIS_USERNAME (Tài khoản LIS)")
                    if (!params.LIS_PASSWORD?.trim()) missingParams.add("LIS_PASSWORD (Mật khẩu LIS)")
                    if (!params.NAME_SPRINT?.trim()) missingParams.add("NAME_SPRINT (Tên Sprint)")
                    if (!params.START_DATE?.trim()) missingParams.add("START_DATE (Release Start Date)")
                    if (!params.DUE_DATE?.trim()) missingParams.add("DUE_DATE (Release Submission Date)")
                    if (!params.ASSIGNEE?.trim()) missingParams.add("ASSIGNEE (Assignee)")
                    if (!params.PROJECT_ID?.trim()) missingParams.add("PROJECT_ID (Project ID Importer)")
                    if (!params.AUTHOR?.trim()) missingParams.add("AUTHOR (Author Importer)")
                    
                    if (missingParams.size() > 0) {
                        error("""
========================================================================
❌ LỖI THIẾU THÔNG TIN BẮT BUỘC!
Vui lòng điền đầy đủ các trường sau trên giao diện Build with Parameters:
- ${missingParams.join('\n- ')}
========================================================================
""")
                    }
                    
                    echo "✅ Tất cả thông tin nhập liệu đã đầy đủ và hợp lệ."
                }
            }
        }

        stage('2. Chuẩn Bị Môi Trường Python & Playwright') {
            steps {
                script {
                    echo "=========================================="
                    echo "🚀 Đang thiết lập môi trường chạy Playwright trên Jenkins..."
                    echo "=========================================="
                    
                    sh '''
                        export PATH="$HOME/.local/bin:$PATH"
                        
                        # 1. Tự động tải và bootstrap pip cho user nếu máy chủ chưa có sẵn pip
                        if ! python3 -m pip --version >/dev/null 2>&1; then
                            echo "[*] Máy chủ chưa có pip, đang tự động tải và cài đặt pip vào ~/.local/bin..."
                            curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py || wget -q https://bootstrap.pypa.io/get-pip.py -O get-pip.py
                            python3 get-pip.py --user --no-warn-script-location
                            rm -f get-pip.py
                        fi
                        
                        # 2. Cài đặt các thư viện cần thiết vào user environment
                        python3 -m pip install --user -r requirements.txt
                        
                        # 3. Tải trình duyệt Chromium cho Playwright
                        python3 -m playwright install chromium
                    '''
                }
            }
        }

        stage('3. Kiểm Tra File Upload & Thực Thi Tự Động Hóa') {
            steps {
                script {
                    echo "=========================================="
                    echo "▶ Tiếp nhận file Excel và khởi chạy tự động hóa..."
                    echo "User LIS: ${params.LIS_USERNAME}"
                    echo "Sprint:   ${params.NAME_SPRINT}"
                    echo "Assignee: ${params.ASSIGNEE}"
                    echo "=========================================="

                    sh '''
                        echo "--- Đang quét tìm 2 file Excel do bạn tải lên trên Jenkins ---"
                        
                        # 1. Tìm file STRUCTURE_FILE_UPLOAD trong workspace hoặc thư mục build của Jenkins
                        if [ -f "STRUCTURE_FILE_UPLOAD" ]; then
                            echo "[✓] Tìm thấy STRUCTURE_FILE_UPLOAD trong workspace."
                            cp -f "STRUCTURE_FILE_UPLOAD" structure_template.xlsx
                        elif [ -f "structure_template.xlsx" ]; then
                            echo "[✓] Đã có file structure_template.xlsx trong workspace."
                        else
                            # Tìm trong thư mục lưu trữ file parameters của Jenkins build
                            FOUND_STRUCT=$(find /var/lib/jenkins -name "STRUCTURE_FILE_UPLOAD" 2>/dev/null | grep "/${BUILD_NUMBER}/" | head -n 1)
                            if [ -z "$FOUND_STRUCT" ]; then
                                FOUND_STRUCT=$(find /var/lib/jenkins -name "STRUCTURE_FILE_UPLOAD" 2>/dev/null | head -n 1)
                            fi
                            if [ -n "$FOUND_STRUCT" ]; then
                                echo "[✓] Đã tìm thấy file Structure trong Jenkins: $FOUND_STRUCT"
                                cp -f "$FOUND_STRUCT" structure_template.xlsx
                            fi
                        fi

                        # 2. Tìm file WORK_ITEMS_FILE_UPLOAD trong workspace hoặc thư mục build của Jenkins
                        if [ -f "WORK_ITEMS_FILE_UPLOAD" ]; then
                            echo "[✓] Tìm thấy WORK_ITEMS_FILE_UPLOAD trong workspace."
                            cp -f "WORK_ITEMS_FILE_UPLOAD LIS_import_WI_Sep01.xlsx"
                        elif [ -f "LIS_import_WI_Sep01.xlsx" ]; then
                            echo "[✓] Đã có file LIS_import_WI_Sep01.xlsx trong workspace."
                        else
                            # Tìm trong thư mục lưu trữ file parameters của Jenkins build
                            FOUND_WI=$(find /var/lib/jenkins -name "WORK_ITEMS_FILE_UPLOAD" 2>/dev/null | grep "/${BUILD_NUMBER}/" | head -n 1)
                            if [ -z "$FOUND_WI" ]; then
                                FOUND_WI=$(find /var/lib/jenkins -name "WORK_ITEMS_FILE_UPLOAD" 2>/dev/null | head -n 1)
                            fi
                            if [ -n "$FOUND_WI" ]; then
                                echo "[✓] Đã tìm thấy file Work Items trong Jenkins: $FOUND_WI"
                                cp -f "$FOUND_WI" LIS_import_WI_Sep01.xlsx
                            fi
                        fi

                        # 3. Quét tất cả file .xlsx nếu có tên khác
                        if [ ! -f "structure_template.xlsx" ] || [ ! -f "LIS_import_WI_Sep01.xlsx" ]; then
                            COUNT=$(find . -maxdepth 2 -name "*.xlsx" | grep -v ".venv" | wc -l)
                            if [ "$COUNT" -ge 2 ]; then
                                FILE1=$(find . -maxdepth 2 -name "*.xlsx" | grep -v ".venv" | sed -n '1p')
                                FILE2=$(find . -maxdepth 2 -name "*.xlsx" | grep -v ".venv" | sed -n '2p')
                                cp -f "$FILE1" structure_template.xlsx
                                cp -f "$FILE2" LIS_import_WI_Sep01.xlsx
                                echo "[✓] Tự động gán 2 file .xlsx tìm thấy: $FILE1 và $FILE2"
                            fi
                        fi

                        # 4. Kiểm tra xác nhận
                        if [ ! -f "structure_template.xlsx" ]; then
                            echo "❌ LỖI: Không tìm thấy file Structure Template trong hệ thống Jenkins!"
                            exit 1
                        fi

                        if [ ! -f "LIS_import_WI_Sep01.xlsx" ]; then
                            echo "❌ LỖI: Không tìm thấy file Work Items trong hệ thống Jenkins!"
                            exit 1
                        fi

                        echo "[✓] Đã nạp thành công 2 file Excel sẵn sàng chạy:"
                        ls -lh structure_template.xlsx LIS_import_WI_Sep01.xlsx
                    '''
                    
                    sh '''
                        export PATH="$HOME/.local/bin:$PATH"
                        
                        export LIS_USERNAME="${LIS_USERNAME}"
                        export LIS_PASSWORD="${LIS_PASSWORD}"
                        export NAME_SPRINT="${NAME_SPRINT}"
                        export START_DATE="${START_DATE}"
                        export DUE_DATE="${DUE_DATE}"
                        export RELEASE_TYPE="${RELEASE_TYPE}"
                        export ENVIRONMENT="${ENVIRONMENT}"
                        export ASSIGNEE="${ASSIGNEE}"
                        export PROJECT_ID="${PROJECT_ID}"
                        export AUTHOR="${AUTHOR}"
                        export STRUCTURE_FILE="structure_template.xlsx"
                        export WORK_ITEMS_FILE="LIS_import_WI_Sep01.xlsx"
                        export HEADLESS="True"
                        
                        python3 main.py sprint_data.json
                    '''
                }
            }
        }
    }

    post {
        always {
            echo "=========================================="
            echo "🏁 Kết thúc tiến trình Build trên Jenkins."
            echo "=========================================="
            // Dọn dẹp các file Excel và session sau khi build xong để bảo mật
            sh '''
                rm -f structure_template.xlsx LIS_import_WI_Sep01.xlsx auth.json
            '''
        }
        success {
            echo "✅ TỰ ĐỘNG HÓA THÀNH CÔNG RỰC RỠ!"
        }
        failure {
            echo "❌ TIẾN TRÌNH THẤT BẠI HOẶC DỪNG DO CÓ LỖI!"
        }
    }
}
