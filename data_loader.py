import os
import json
from pathlib import Path
from typing import Any
import config


def load_milestone_from_file(file_path: str = "sprint_data.json") -> dict[str, Any]:
    """Đọc dữ liệu sprint/milestone từ file JSON. Hỗ trợ nhiều cách phân giải đường dẫn."""
    p = Path(file_path)
    
    if p.exists() and p.is_file():
        path = p
    elif (config.BASE_DIR / file_path).exists() and (config.BASE_DIR / file_path).is_file():
        path = config.BASE_DIR / file_path
    elif (config.BASE_DIR / p.name).exists() and (config.BASE_DIR / p.name).is_file():
        path = config.BASE_DIR / p.name
    elif hasattr(config, "PROJECT_ROOT") and (config.PROJECT_ROOT / file_path).exists() and (config.PROJECT_ROOT / file_path).is_file():
        path = config.PROJECT_ROOT / file_path
    else:
        fallback = config.BASE_DIR / "milestone_data.json"
        if fallback.exists():
            path = fallback
        else:
            raise FileNotFoundError(f"Không tìm thấy file dữ liệu JSON: {file_path}")

    if path.suffix.lower() != ".json":
        raise ValueError(f"Chỉ hỗ trợ file định dạng .json (nhận được: {path.suffix})")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {}
    if isinstance(data, dict):
        result = data
    elif isinstance(data, list) and len(data) > 0:
        if not isinstance(data[0], dict):
            raise ValueError("Phần tử đầu tiên trong mảng JSON phải là object (dict).")
        result = data[0]
    else:
        raise ValueError("File JSON không chứa dữ liệu hợp lệ.")

    # Tự động ghi đè từ biến môi trường Jenkins (Build with Parameters)
    env_mapping = {
        "Name Sprint": ["NAME_SPRINT", "SPRINT_NAME"],
        "Release Start Date": ["RELEASE_START_DATE", "START_DATE"],
        "Release Submission Date": ["RELEASE_SUBMISSION_DATE", "DUE_DATE", "SUBMISSION_DATE"],
        "Release Type": ["RELEASE_TYPE"],
        "Environment": ["ENVIRONMENT", "ENV"],
        "Assignee": ["ASSIGNEE"],
        "Project ID Importer": ["PROJECT_ID_IMPORTER", "PROJECT_ID"],
        "Author Importer": ["AUTHOR_IMPORTER", "AUTHOR"],
        "Upload File": ["UPLOAD_FILE", "STRUCTURE_FILE"],
        "Upload Work Items File": ["UPLOAD_WORK_ITEMS_FILE", "WORK_ITEMS_FILE"]
    }
    for key, env_vars in env_mapping.items():
        for env_var in env_vars:
            val = os.getenv(env_var)
            if val is not None and val != "":
                result[key] = val
                break

    # Kiểm tra các trường bắt buộc
    required_fields = [
        "Name Sprint",
        "Release Start Date",
        "Release Submission Date",
        "Assignee",
        "Project ID Importer",
        "Author Importer",
        "Upload File",
        "Upload Work Items File"
    ]
    missing = [f for f in required_fields if not result.get(f) or str(result.get(f)).strip() == ""]
    if missing:
        raise ValueError(f"Thiếu các trường thông tin bắt buộc: {', '.join(missing)}. Vui lòng điền đầy đủ tham số!")

    return result


if __name__ == "__main__":
    print("Dữ liệu nạp từ JSON:", load_milestone_from_file("sprint_data.json"))
