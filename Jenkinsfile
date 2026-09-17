pipeline {
    agent any

    parameters {
        choice(
            name: 'EXECUTION_MODE',
            choices: ['ALL (Phase 1 + Phase 2)', 'PHASE_1_ONLY', 'PHASE_2_ONLY'],
            description: '''Chọn chế độ thực thi:
• ALL (Phase 1 + Phase 2) (Mặc định): Chạy toàn trình từ A đến Z (Tạo Sprint, nạp 2 file Excel, lọc task, gán Milestone/Sprint và xác minh database).
• PHASE_1_ONLY: Chỉ tạo Sprint và nạp Excel (dành cho khi bạn chỉ muốn import).
• PHASE_2_ONLY: Chỉ lọc task và gán Milestone/Sprint (không cần chọn file Excel, tiện lợi khi muốn chạy lại Phase 2).'''
        )
        string(name: 'LIS_USERNAME', defaultValue: '', description: 'LIS Username')
        password(name: 'LIS_PASSWORD', defaultValue: '', description: 'LIS Password')
        string(name: 'SPRINT_NAME', defaultValue: '', description: 'Sprint Name')
        string(name: 'START_DATE', defaultValue: '', description: 'Release Start Date (YYYY-MM-DD)')
        string(name: 'DUE_DATE', defaultValue: '', description: 'Release Submission Date (YYYY-MM-DD)')
        choice(name: 'RELEASE_TYPE', choices: ['Internal', 'External', ''], description: 'Release Type')
        choice(name: 'ENVIRONMENT', choices: ['Development', 'Testing', 'Production', 'Local'], description: 'Environment')
        string(name: 'ASSIGNEE', defaultValue: '', description: 'Assignee (e.g. Trang Pham-Tran-Minh)')
        string(name: 'PROJECT_ID', defaultValue: '', description: 'Project ID On LIS (e.g. 786 for Team MAX)')
        // 2 file Excel nạp vào hệ thống (chỉ bắt buộc khi chạy Phase 1 hoặc ALL)
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
                    echo "🔍 Đang kiểm tra thông tin nhập liệu (Chế độ: ${params.EXECUTION_MODE})..."
                    echo "=========================================="
                    
                    def missingParams = []
                    
                    // Các trường bắt buộc dùng chung cho cả 2 Phase
                    if (!params.LIS_USERNAME?.trim()) missingParams.add("LIS_USERNAME (Tài khoản LIS)")
                    if (!params.LIS_PASSWORD?.toString()?.trim()) missingParams.add("LIS_PASSWORD (Mật khẩu LIS)")
                    if (!params.PROJECT_ID?.trim()) missingParams.add("PROJECT_ID (Project ID ON LIS)")
                    if (!params.SPRINT_NAME?.trim()) missingParams.add("SPRINT_NAME (Tên Sprint)")
                    if (!params.START_DATE?.trim()) missingParams.add("START_DATE (Release Start Date)")
                    if (!params.DUE_DATE?.trim()) missingParams.add("DUE_DATE (Release Submission Date)")
                    
                    // Trường bắt buộc khi chạy Phase 1 hoặc ALL
                    if (params.EXECUTION_MODE != 'PHASE_2_ONLY') {
                        if (!params.ASSIGNEE?.trim()) missingParams.add("ASSIGNEE (Người phụ trách Parent Task)")
                    }
                    
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

        stage('3. Thực Thi Phase 1 (Sprint Setup & Excel Import)') {
            when {
                expression { params.EXECUTION_MODE == 'ALL (Phase 1 + Phase 2)' || params.EXECUTION_MODE == 'PHASE_1_ONLY' }
            }
            steps {
                script {
                    echo "=========================================="
                    echo "▶ [PHASE 1] Khởi chạy tạo Sprint, Parent Task và nạp 2 file Excel..."
                    echo "User LIS:   ${params.LIS_USERNAME}"
                    echo "Sprint:     ${params.SPRINT_NAME}"
                    echo "Assignee:   ${params.ASSIGNEE}"
                    echo "Project ID: ${params.PROJECT_ID}"
                    echo "=========================================="

                    withFileParameter('STRUCTURE_FILE') {
                        withFileParameter('WORK_ITEMS_FILE') {
                            sh '''
                                export PATH="$HOME/.local/bin:$PATH"
                                
                                # Kiểm tra sự tồn tại của 2 file Excel tải lên
                                if [ ! -f "$STRUCTURE_FILE" ] || [ ! -s "$STRUCTURE_FILE" ]; then
                                    echo "❌ [LỖI] File STRUCTURE_FILE trống hoặc chưa được chọn!"
                                    exit 1
                                fi
                                if [ ! -f "$WORK_ITEMS_FILE" ] || [ ! -s "$WORK_ITEMS_FILE" ]; then
                                    echo "❌ [LỖI] File WORK_ITEMS_FILE trống hoặc chưa được chọn!"
                                    exit 1
                                fi
                                
                                # Chuẩn hóa 2 file tải lên sang định dạng Excel .xlsx hợp lệ cho Importer
                                cp -f "$STRUCTURE_FILE" "structure_template.xlsx"
                                cp -f "$WORK_ITEMS_FILE" "work_items_detail.xlsx"
                                
                                echo "=========================================="
                                echo "📁 [✓] TIẾP NHẬN FILE THÀNH CÔNG:"
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

        stage('4. Thực Thi Phase 2 (Task Filtering & Bulk Assign Milestone/Sprint)') {
            when {
                expression { params.EXECUTION_MODE == 'ALL (Phase 1 + Phase 2)' || params.EXECUTION_MODE == 'PHASE_2_ONLY' }
            }
            steps {
                script {
                    echo "=========================================="
                    echo "▶ [PHASE 2] Khởi chạy lọc Task và gán Target Milestone / Sprint..."
                    echo "User LIS:   ${params.LIS_USERNAME}"
                    echo "Project ID: ${params.PROJECT_ID}"
                    echo "Sprint:     ${params.SPRINT_NAME}"
                    echo "Start Date: ${params.START_DATE}"
                    echo "Due Date:   ${params.DUE_DATE}"
                    echo "=========================================="

                    sh '''
                        export PATH="$HOME/.local/bin:$PATH"
                        
                        # Nếu vừa chạy xong Phase 1 trong chế độ ALL, nghỉ 5 giây để LIS đồng bộ dữ liệu
                        if [ "${EXECUTION_MODE}" = "ALL (Phase 1 + Phase 2)" ]; then
                            echo "[*] Đợi 5 giây để dữ liệu hoàn tất đồng bộ trên LIS trước khi lọc..."
                            sleep 5
                        fi
                        
                        export LIS_USERNAME="${LIS_USERNAME}"
                        export LIS_PASSWORD="${LIS_PASSWORD}"
                        export PROJECT_ID="${PROJECT_ID}"
                        export SPRINT_NAME="${SPRINT_NAME}"
                        export START_DATE="${START_DATE}"
                        export DUE_DATE="${DUE_DATE}"
                        export HEADLESS="True"
                        
                        python3 main_phase2.py
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
            // In báo cáo tổng kết tình trạng import (nếu có) và dọn dẹp file tạm
            sh '''
                if [ -f import_summary.txt ]; then
                    echo ""
                    cat import_summary.txt
                    echo ""
                    rm -f import_summary.txt
                fi
                rm -f *.xlsx auth.json
            '''
        }
        success {
            echo "✅ TỰ ĐỘNG HÓA HOÀN TẤT THÀNH CÔNG RỰC RỠ!"
        }
        failure {
            echo "❌ TIẾN TRÌNH THẤT BẠI HOẶC DỪNG DO CÓ LỖI!"
        }
    }
}
