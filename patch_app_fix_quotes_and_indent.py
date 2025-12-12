#!/usr/bin/env python3
# patch_app_fix_quotes_and_indent.py
# Usage:
#   python patch_app_fix_quotes_and_indent.py "C:\Users\hp\Desktop\survey_app\app.py"
import sys, re, io, os
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python patch_app_fix_quotes_and_indent.py <path-to-app.py>")
        sys.exit(1)
    path = Path(sys.argv[1])
    src = path.read_text(encoding="utf-8", errors="ignore")

    orig = src

    # 1) Unescape triple quotes in SQL execute blocks
    # common bad patterns: c.execute(\"\"\"  ...  \"\"\")
    src = src.replace('c.execute(\\\"\\\"\\\"', 'c.execute(\"\"\"')
    src = src.replace('\\\"\\\"\\\")', '\"\"\")')
    # generic: remove backslashes right before triple quotes
    src = re.sub(r'\\+\"\"\"', '\"\"\"', src)

    # 2) Insert 'pass' after any lone 'if ...:' that is immediately followed by a route decorator
    def add_pass_after_if(m):
        if_line = m.group(1)
        return if_line + "\n    pass"
    src = re.sub(
        r'(^[ \t]*if[^\n]*:\s*)(\n[ \t]*@app\.route\()',
        lambda m: m.group(1) + "\n    pass" + m.group(2),
        src,
        flags=re.MULTILINE
    )

    # 3) Ensure payout routes are top-level (remove accidental leading spaces)
    src = re.sub(r'^[ \t]+(@app\.route\(\"/api/payout/provider/<int:pid>/fields\"\))', r'\1', src, flags=re.MULTILINE)
    src = re.sub(r'^[ \t]+(def api_payout_provider_fields\(pid\):)', r'\1', src, flags=re.MULTILINE)
    src = re.sub(r'^[ \t]+(@app\.route\(\"/wallet/payout\", methods=\[\"GET\",\"POST\"\]\))', r'\1', src, flags=re.MULTILINE)
    src = re.sub(r'^[ \t]+(def wallet_payout\(\):)', r'\1', src, flags=re.MULTILINE)

    if src != orig:
        backup = path.with_suffix(".py.bak")
        backup.write_text(orig, encoding="utf-8")
        path.write_text(src, encoding="utf-8")
        print(f"[OK] Patched {path}\nBackup written to {backup}")
    else:
        print("[INFO] No changes applied (file already clean).")

if __name__ == "__main__":
    main()
