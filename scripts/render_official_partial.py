from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "android-pack" / "launcher-mappings" / "icons.json"
OFFICIAL = ROOT / "artwork" / "official"

original_text = ICONS.read_text(encoding="utf-8")
all_icons = json.loads(original_text)


def has_official(slug: str) -> bool:
    return any((OFFICIAL / f"{slug}{suffix}").exists() for suffix in (".svg", ".png", ".webp", ".jpg", ".jpeg"))


filtered = {slug: cfg for slug, cfg in all_icons.items() if has_official(slug)}
missing = sorted(set(all_icons) - set(filtered))
if not filtered:
    raise RuntimeError("no official artwork resolved; refusing to render")

try:
    ICONS.write_text(json.dumps(filtered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "renderer" / "offline_renderer" / "render.py"), "--all"], cwd=ROOT, check=True)
finally:
    ICONS.write_text(original_text, encoding="utf-8")

print("partial official render:", ", ".join(sorted(filtered)))
if missing:
    print("excluded unresolved:", ", ".join(missing))
