from scripts import sync_official_assets as sync

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
