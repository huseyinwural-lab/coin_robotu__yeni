from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.backup_service import upload_backup_to_s3


def _s3_upload_required() -> bool:
    return (os.getenv("BACKUP_S3_UPLOAD_REQUIRED") or "").strip() == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload DB backup file to AWS S3")
    parser.add_argument("backup_file_path", help="Absolute or relative path to .sql backup file")
    args = parser.parse_args()

    result = upload_backup_to_s3(args.backup_file_path)

    if result.status == "uploaded":
        print(f"S3_UPLOAD_OK uri={result.s3_uri}")
        return 0

    if result.status == "skipped":
        print(f"S3_UPLOAD_SKIPPED reason={result.message}")
        if _s3_upload_required():
            print("S3_UPLOAD_REQUIRED_BUT_SKIPPED")
            return 1
        return 0

    print(f"S3_UPLOAD_FAIL reason={result.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
