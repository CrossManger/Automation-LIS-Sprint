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
        string(name: 'ASSIGNEE', defaultValue: '', description: 'Assignee (e.g: Trang Pham-Tran-Minh)')
        string(name: 'PROJECT_ID', defaultValue: '', description: 'Project ID Importer (e.g: 786 for Team MAX)')
        string(name: 'AUTHOR', defaultValue: '', description: 'Author Importer (e.g: trangptm)')
        
        // Sử dụng base64File (tương thích 100% với withFileParameter của Jenkins Pipeline)
        base64File(name: 'STRUCTURE_FILE', description: 'Structure File (Template)')
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

        stage('3. Tiếp Nhận File Upload & Thực Thi Tự Động Hóa') {
            steps {
                script {
                    echo "=========================================="
                    echo "▶ Tiếp nhận 2 file Excel và khởi chạy tự động hóa..."
                    echo "User LIS: ${params.LIS_USERNAME}"
                    echo "Sprint:   ${params.NAME_SPRINT}"
                    echo "Assignee: ${params.ASSIGNEE}"
                    echo "=========================================="

                    withFileParameter('STRUCTURE_FILE') {
                        withFileParameter('WORK_ITEMS_FILE') {
                            sh '''
                                export PATH="$HOME/.local/bin:$PATH"
                                
                                # Copy file từ withFileParameter vào workspace
                                cp -f "$STRUCTURE_FILE" structure_template.xlsx
                                cp -f "$WORK_ITEMS_FILE" LIS_import_WI_Sep01.xlsx
                                
                                echo "[✓] Đã tiếp nhận thành công 2 file Excel upload:"
                                ls -lh structure_template.xlsx LIS_import_WI_Sep01.xlsx
                                
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
