pipeline {
    agent any

    parameters {
        // Tất cả các tham số đều để trống (không có defaultValue), bắt buộc người dùng phải nhập
        string(name: 'NAME_SPRINT', defaultValue: '', description: 'Tên Sprint (Name Sprint)* [BẮT BUỘC - Ví dụ: 2026 Oct 01 Sprint]')
        string(name: 'START_DATE', defaultValue: '', description: 'Release Start Date (YYYY-MM-DD)* [BẮT BUỘC - Ví dụ: 2026-10-01]')
        string(name: 'DUE_DATE', defaultValue: '', description: 'Release Submission Date (YYYY-MM-DD)* [BẮT BUỘC - Ví dụ: 2026-10-17]')
        choice(name: 'RELEASE_TYPE', choices: ['Internal', 'External', ''], description: 'Release Type')
        choice(name: 'ENVIRONMENT', choices: ['Development', 'Testing', 'Production', 'Local'], description: 'Environment')
        string(name: 'ASSIGNEE', defaultValue: '', description: 'Assignee (Người được giao)* [BẮT BUỘC - Ví dụ: Trang Pham-Tran-Minh]')
        string(name: 'PROJECT_ID', defaultValue: '', description: 'Project ID Importer* [BẮT BUỘC - Ví dụ: 786]')
        string(name: 'AUTHOR', defaultValue: '', description: 'Author Importer* [BẮT BUỘC - Ví dụ: minhvh]')
        
        // Bắt buộc người dùng tải trực tiếp 2 file Excel từ máy tính lên Jenkins
        file(name: 'STRUCTURE_FILE_UPLOAD', description: '📁 Tải lên file Structure Template (.xlsx)* [BẮT BUỘC]')
        file(name: 'WORK_ITEMS_FILE_UPLOAD', description: '📁 Tải lên file Work Items (.xlsx)* [BẮT BUỘC]')
        
        string(name: 'LIS_CREDENTIALS_ID', defaultValue: '', description: 'ID lưu Username/Password trong Jenkins Credentials* [BẮT BUỘC - Ví dụ: lis_credentials]')
    }

    environment {
        HEADLESS = 'True'
        PYTHONUNBUFFERED = '1'
        CI = 'true'
    }

    stages {
        stage('1. Kiểm Tra Tính Hợp Lệ Của Tham Số (Validate Parameters)') {
            steps {
                script {
                    echo "=========================================="
                    echo "🔍 Đang kiểm tra các tham số đầu vào..."
                    echo "=========================================="
                    
                    def missingParams = []
                    
                    if (!params.NAME_SPRINT?.trim()) missingParams.add("NAME_SPRINT (Tên Sprint)")
                    if (!params.START_DATE?.trim()) missingParams.add("START_DATE (Release Start Date)")
                    if (!params.DUE_DATE?.trim()) missingParams.add("DUE_DATE (Release Submission Date)")
                    if (!params.ASSIGNEE?.trim()) missingParams.add("ASSIGNEE (Assignee)")
                    if (!params.PROJECT_ID?.trim()) missingParams.add("PROJECT_ID (Project ID Importer)")
                    if (!params.AUTHOR?.trim()) missingParams.add("AUTHOR (Author Importer)")
                    if (!params.LIS_CREDENTIALS_ID?.trim()) missingParams.add("LIS_CREDENTIALS_ID (Jenkins Credentials ID)")
                    
                    if (missingParams.size() > 0) {
                        error("""
========================================================================
❌ LỖI THIẾU THAM SỐ BẮT BUỘC!
Hệ thống không cho phép dùng giá trị mặc định. Vui lòng nhập đầy đủ các trường sau:
- ${missingParams.join('\n- ')}
========================================================================
""")
                    }
                    
                    echo "✅ Tất cả các tham số nhập liệu đã hợp lệ."
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
                        if [ ! -d ".venv" ]; then
                            python3 -m venv .venv
                        fi
                        
                        . .venv/bin/activate
                        pip install --upgrade pip
                        pip install -r requirements.txt
                        playwright install chromium
                    '''
                }
            }
        }

        stage('3. Kiểm Tra File Upload & Thực Thi Tự Động Hóa') {
            steps {
                script {
                    echo "=========================================="
                    echo "▶ Kiểm tra 2 file Excel upload và khởi chạy..."
                    echo "Sprint:   ${params.NAME_SPRINT}"
                    echo "Assignee: ${params.ASSIGNEE}"
                    echo "=========================================="

                    // Kiểm tra bắt buộc phải có 2 file Excel do người dùng upload
                    sh '''
                        if [ ! -f "STRUCTURE_FILE_UPLOAD" ]; then
                            echo "❌ LỖI: Bạn chưa tải lên file Structure Template (.xlsx)!"
                            exit 1
                        fi
                        
                        if [ ! -f "WORK_ITEMS_FILE_UPLOAD" ]; then
                            echo "❌ LỖI: Bạn chưa tải lên file Work Items (.xlsx)!"
                            exit 1
                        fi
                        
                        # Đổi tên file upload thành file chuẩn để script Python xử lý
                        mv -f STRUCTURE_FILE_UPLOAD structure_template.xlsx
                        mv -f WORK_ITEMS_FILE_UPLOAD LIS_import_WI_Sep01.xlsx
                        echo "[✓] Đã tiếp nhận và chuẩn bị sẵn sàng 2 file Excel."
                    '''
                    
                    // Nạp Username / Password từ Jenkins Credentials
                    withCredentials([usernamePassword(credentialsId: params.LIS_CREDENTIALS_ID.trim(), usernameVariable: 'LIS_USERNAME', passwordVariable: 'LIS_PASSWORD')]) {
                        sh '''
                            . .venv/bin/activate
                            
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
                            export LIS_USERNAME="${LIS_USERNAME}"
                            export LIS_PASSWORD="${LIS_PASSWORD}"
                            export HEADLESS="True"
                            
                            python main.py sprint_data.json
                        '''
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
            // Dọn dẹp các file Excel sau khi build xong để bảo mật
            sh '''
                rm -f structure_template.xlsx LIS_import_WI_Sep01.xlsx auth.json
            '''
        }
        success {
            echo "✅ TỰ ĐỘNG HÓA THÀNH CÔNG RỰC RỠ!"
        }
        failure {
            echo "❌ TIẾN TRÌNH THẤT BẠI HOẶC DỪNG DO THIẾU THAM SỐ BẮT BUỘC!"
        }
    }
}
