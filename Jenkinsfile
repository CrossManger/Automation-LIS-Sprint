pipeline {
    agent any

    parameters {
        string(name: 'LIS_USERNAME', defaultValue: '', description: 'LIS Username')
        password(name: 'LIS_PASSWORD', defaultValue: '', description: 'LIS Password')
        string(name: 'SPRINT_NAME', defaultValue: '', description: 'Sprint Name')
        string(name: 'START_DATE', defaultValue: '', description: 'Release Start Date (YYYY-MM-DD)')
        string(name: 'DUE_DATE', defaultValue: '', description: 'Release Submission Date (YYYY-MM-DD)')
        choice(name: 'RELEASE_TYPE', choices: ['Internal', 'External', ''], description: 'Release Type')
        choice(name: 'ENVIRONMENT', choices: ['Development', 'Testing', 'Production', 'Local'], description: 'Environment')
        string(name: 'ASSIGNEE', defaultValue: '', description: 'Assignee (e.g. Trang Pham-Tran-Minh)')
        string(name: 'PROJECT_ID', defaultValue: '', description: 'Project ID On LIS (e.g. 786 for Team MAX)')
        
        // Nhận 2 file Excel trực tiếp từ máy tính của người dùng
        base64File(name: 'STRUCTURE_FILE', description: 'Base Structure Template')
        base64File(name: 'WORK_ITEMS_FILE', description: 'Work Items File')
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
                    if (!params.LIS_PASSWORD?.toString()?.trim()) missingParams.add("LIS_PASSWORD (Mật khẩu LIS)")
                    if (!params.SPRINT_NAME?.trim()) missingParams.add("SPRINT_NAME (Tên Sprint)")
                    if (!params.START_DATE?.trim()) missingParams.add("START_DATE (Release Start Date)")
                    if (!params.DUE_DATE?.trim()) missingParams.add("DUE_DATE (Release Submission Date)")
                    if (!params.ASSIGNEE?.trim()) missingParams.add("ASSIGNEE (Assignee)")
                    if (!params.PROJECT_ID?.trim()) missingParams.add("PROJECT_ID (Project ID ON LIS)")
                    
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

        stage('3. Tiếp Nhận File Upload & Thực Thi Tự Động Hóa') {
            steps {
                script {
                    echo "=========================================="
                    echo "▶ Tiếp nhận thông tin và khởi chạy tự động hóa..."
                    echo "User LIS:   ${params.LIS_USERNAME}"
                    echo "Sprint:     ${params.SPRINT_NAME}"
                    echo "Assignee:   ${params.ASSIGNEE}"
                    echo "Project ID: ${params.PROJECT_ID}"
                    echo "=========================================="

                    withFileParameter('STRUCTURE_FILE') {
                        withFileParameter('WORK_ITEMS_FILE') {
                            sh '''
                                export PATH="$HOME/.local/bin:$PATH"
                                
                                # Chuẩn hóa 2 file tải lên sang định dạng Excel .xlsx hợp lệ cho Importer
                                cp -f "$STRUCTURE_FILE" "structure_template.xlsx"
                                cp -f "$WORK_ITEMS_FILE" "work_items_detail.xlsx"
                                
                                echo "=========================================="
                                echo "📁 [✓] TIẾP NHẬN THÀNH CÔNG:"
                                echo "  1. File Cấu trúc Sprint (Tầng 1)"
                                echo "  2. File Chi tiết Work Items (Tầng 2)"
                                echo "=========================================="
                                
                                export LIS_USERNAME="${LIS_USERNAME}"
                                export LIS_PASSWORD="${LIS_PASSWORD}"
                                export SPRINT_NAME="${SPRINT_NAME}"
                                export START_DATE="${START_DATE}"
                                export DUE_DATE="${DUE_DATE}"
                                export RELEASE_TYPE="${RELEASE_TYPE}"
                                export ENVIRONMENT="${ENVIRONMENT}"
                                export ASSIGNEE="${ASSIGNEE}"
                                export PROJECT_ID="${PROJECT_ID}"
                                export AUTHOR="${LIS_USERNAME}"
                                export STRUCTURE_FILE="structure_template.xlsx"
                                export WORK_ITEMS_FILE="work_items_detail.xlsx"
                                export HEADLESS="True"
                                
                                python3 main.py
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            echo "=========================================="
            echo "🏁 Kết thúc tiến trình Build trên Jenkins."
            echo "=========================================="
            // Dọn dẹp tất cả các file Excel mà người dùng vừa tải lên và file session auth.json
            sh '''
                rm -f *.xlsx auth.json
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
