
import os, re, shutil
from pathlib import Path

TEMPLATES_DIR = Path(r"C:\Users\hp\Desktop\survey_app\templates")  # <-- adjust if needed

HEAD_BLOCK_RE = re.compile(r"{%\\s*block\\s+head_extra\\s*%}(.*?){%\\s*endblock\\s*%}", re.DOTALL)

def ensure_single_head_block(base_path: Path):
    if not base_path.exists():
        print(f"[WARN] base.html not found at: {base_path}")
        return
    text = base_path.read_text(encoding="utf-8", errors="ignore")
    # Remove duplicates: keep the first, drop others.
    blocks = list(HEAD_BLOCK_RE.finditer(text))
    if len(blocks) == 0:
        # Insert before </head>
        insertion = "\n  {% block head_extra %}{% endblock %}\n"
        text = text.replace("</head>", insertion + "</head>")
        base_path.write_text(text, encoding="utf-8")
        print("[OK] Added head_extra block to base.html")
    elif len(blocks) > 1:
        # Keep first, remove others
        first = blocks[0]
        new_text = text[:first.start()] + first.group(0) + HEAD_BLOCK_RE.sub("", text[first.end():], count=0)
        base_path.write_text(new_text, encoding="utf-8")
        print("[OK] Reduced duplicate head_extra blocks to one in base.html")
    else:
        print("[OK] base.html already has a single head_extra block")

def super_safe_replace(block_content: str) -> str:
    # Replace direct super() calls ONLY within the block to a never-called expression
    # to avoid UndefinedError when no parent block exists in the chain.
    # We preserve surrounding content.
    # Examples replaced:
    #   {{ super() }}
    #   {{  super()  }}
    # We'll replace with: {{ (false and super()) or '' }}
    content = re.sub(r"{{\\s*super\\(\\)\\s*}}", "{{ (false and super()) or '' }}", block_content)
    return content

def make_head_blocks_super_safe(path: Path):
    txt = path.read_text(encoding="utf-8", errors="ignore")
    changed = False
    def _one(m):
        nonlocal changed
        inner = m.group(1)
        new_inner = super_safe_replace(inner)
        if new_inner != inner:
            changed = True
        return "{% block head_extra %}" + new_inner + "{% endblock %}"
    new_txt = HEAD_BLOCK_RE.sub(_one, txt)
    if changed:
        # backup once
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copyfile(path, bak)
        path.write_text(new_txt, encoding="utf-8")
        print(f"[FIXED] super() guarded in: {path.name}")
    else:
        print(f"[OK] no super() or already safe: {path.name}")

def main():
    base = TEMPLATES_DIR / "base.html"
    ensure_single_head_block(base)

    for p in TEMPLATES_DIR.rglob("*.html"):
        make_head_blocks_super_safe(p)

if __name__ == "__main__":
    main()
