from __future__ import annotations

import importlib.util
import json
from pathlib import Path

source_file = Path(__file__).with_name("sync_official_assets.py")
spec = importlib.util.spec_from_file_location("sync_official_assets", source_file)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {source_file}")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

_original_fetch = sync.fetch


def _fetch_with_android_cn_mirror(url: str):
    if url.startswith("https://developer.android.com/"):
        url = url.replace("https://developer.android.com/", "https://developer.android.google.cn/", 1)
        if "?" not in url:
            url += "?hl=en"
        elif "hl=" not in url:
            url += "&hl=en"
    return _original_fetch(url)


sync.fetch = _fetch_with_android_cn_mirror

# Build a truthful partial official-source cache even when Google's current
# Play prism download cannot be resolved automatically. This is only for
# visual source validation; the strict validator still requires all 9 icons.
for p in sync.OUT.iterdir():
    if p.is_file() and p.name != "README.md":
        p.unlink()

records = {
    "telegram": sync.sync_telegram(),
    "github": sync.sync_github(),
    "revanced": sync.sync_revanced(),
}
for slug, page in sync.PLAY_PAGES.items():
    records[slug] = sync.play_icon(slug, page)

unresolved = {}
try:
    records["google_play"] = sync.google_play_prism()
except Exception as exc:
    unresolved["google_play"] = str(exc)

(sync.OUT / "provenance.json").write_text(
    json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    encoding="utf-8",
)
(sync.OUT / "unresolved.json").write_text(
    json.dumps(unresolved, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    encoding="utf-8",
)
print("official source sync:", ", ".join(sorted(records)))
if unresolved:
    print("UNRESOLVED:", json.dumps(unresolved, ensure_ascii=False))
