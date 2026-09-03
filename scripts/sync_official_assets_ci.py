from __future__ import annotations

import importlib.util
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
sync.main()
