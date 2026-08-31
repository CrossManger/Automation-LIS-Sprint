import os
import json
from pathlib import Path
from typing import Any
import config


def load_milestone_from_file(file_path: str | None = None) -> dict[str, Any]:
    """Nạp dữ liệu sprint/milestone từ file JSON hoặc trực tiếp từ biến môi trường Jenkins."""
    result: dict[str, Any] = {}

    if file_path:
        p = Path(file_path)
        path = None
        if p.exists() and p.is_file():
            path = p
        elif (config.BASE_DIR / file_path).exists() and (config.BASE_DIR / file_path).is_file():
            path = config.BASE_DIR / file_path
        elif (config.BASE_DIR / p.name).exists() and (config.BASE_DIR / p.name).is_file():
            path = config.BASE_DIR / p.name

        if path and path.suffix.lower() == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    result = data
                elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    result = data[0]
            except Exception:
                pass

    # Nạp và ghi đè từ biến môi trường Jenkins (Build with Parameters)
    env_mapping = {
        "Name Sprint": ["NAME_SPRINT", "SPRINT_NAME"],
        "Release Start Date": ["RELEASE_START_DATE", "START_DATE"],
        "Release Submission Date": ["RELEASE_SUBMISSION_DATE", "DUE_DATE", "SUBMISSION_DATE"],
        "Release Type": ["RELEASE_TYPE"],
        "Environment": ["ENVIRONMENT", "ENV"],
        "Assignee": ["ASSIGNEE"],
        "Project ID Importer": ["PROJECT_ID_IMPORTER", "PROJECT_ID"],
        "Author Importer": ["AUTHOR_IMPORTER", "AUTHOR", "LIS_USERNAME"],
        "Upload File": ["UPLOAD_FILE", "STRUCTURE_FILE"],
        "Upload Work Items File": ["UPLOAD_WORK_ITEMS_FILE", "WORK_ITEMS_FILE"]
    }
    for key, env_vars in env_mapping.items():
        for env_var in env_vars:
            val = os.getenv(env_var)
            if val is not None and val != "":
                result[key] = val
                break

    # Tự động gán Author Importer bằng LIS_USERNAME nếu chưa có
    if not result.get("Author Importer"):
        result["Author Importer"] = os.getenv("LIS_USERNAME") or config.LIS_USERNAME or ""

    # Đặt giá trị mặc định cho file nếu chưa có
    if not result.get("Upload File"):
        result["Upload File"] = "structure_template.xlsx"
    if not result.get("Upload Work Items File"):
        result["Upload Work Items File"] = "LIS_import_WI_Sep01.xlsx"

    # Kiểm tra các trường bắt buộc
    required_fields = [
        "Name Sprint",
        "Release Start Date",
        "Release Submission Date",
        "Assignee",
        "Project ID Importer"
    ]
    missing = [f for f in required_fields if not result.get(f) or str(result.get(f)).strip() == ""]
    if missing:
        raise ValueError(f"Thiếu các trường thông tin bắt buộc: {', '.join(missing)}. Vui lòng điền đầy đủ tham số!")

    return result


if __name__ == "__main__":
    import sys
    try:
        print("Dữ liệu nạp:", load_milestone_from_file())
    except Exception as e:
        print(f"[X] LỖI NẠP DỮ LIỆU: {e}")
        sys.exit(1)
