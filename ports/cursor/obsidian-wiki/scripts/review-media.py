#!/usr/bin/env python3
"""Report media review state; OCR is optional and never evidence by itself."""
import argparse, json, shutil
ap=argparse.ArgumentParser(); ap.add_argument("path"); ap.add_argument("--json", action="store_true"); a=ap.parse_args()
out={"review_status":"manual-review-required","ocr":{"status":"unavailable" if not shutil.which("tesseract") else "not-run"}}
print(json.dumps(out, sort_keys=True) if a.json else out["review_status"])
