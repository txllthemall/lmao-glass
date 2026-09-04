from __future__ import annotations

import hashlib
import html
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artwork" / "official"
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 lmao-glass-source-sync/1.0"

TELEGRAM_COMMIT = "62b56a07ca7e30e39f7fd00a6728d6bbd716ca1c"
OCTICONS_COMMIT = "0e21a4c2d8449102f10e533d241f04797af0914c"
REVANCED_COMMIT = "73b3a5605e20f140994ecc08d232d6d921fa4bcf"
PLAY_PAGES = {
    "discord": "https://play.google.com/store/apps/details?id=com.discord&hl=en&gl=US",
    "pinterest": "https://play.google.com/store/apps/details?id=com.pinterest&hl=en&gl=US",
    "kaspi": "https://play.google.com/store/apps/details?id=kz.kaspi.mobile&hl=en&gl=US",
    "2gis": "https://play.google.com/store/apps/details?id=ru.dublgis.dgismobile&hl=en&gl=US",
    "gamehub": "https://play.google.com/store/apps/details?id=com.xiaoji.egggame&hl=en&gl=US",
}


def fetch(url: str) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        return data, response.geturl(), content_type


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_bytes(slug: str, suffix: str, data: bytes) -> Path:
    path = OUT / f"{slug}{suffix}"
    path.write_bytes(data)
    return path


def save_png(slug: str, data: bytes) -> Path:
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    path = OUT / f"{slug}.png"
    image.save(path, "PNG", optimize=True)
    return path


class AssetHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_images: list[str] = []
        self.icon_images: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            prop = (a.get("property") or a.get("name") or "").lower()
            if prop in {"og:image", "twitter:image"} and a.get("content"):
                self.meta_images.append(a["content"])
        elif tag.lower() == "img":
            alt = a.get("alt", "").strip().lower()
            src = a.get("src") or a.get("data-src") or a.get("srcset", "").split(" ", 1)[0]
            if src and ("icon image" in alt or alt == "app icon"):
                self.icon_images.append(src)
        elif tag.lower() == "a":
            self._anchor_href = a.get("href")
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchor_href is not None:
            self.links.append((self._anchor_href, " ".join(self._anchor_text).strip()))
            self._anchor_href = None
            self._anchor_text = []


def parse_html(data: bytes) -> AssetHTMLParser:
    parser = AssetHTMLParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    return parser


def android_vector_to_svg(xml_bytes: bytes) -> bytes:
    root = ET.fromstring(xml_bytes)
    ns = "{http://schemas.android.com/apk/res/android}"
    vw = root.attrib[ns + "viewportWidth"]
    vh = root.attrib[ns + "viewportHeight"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {html.escape(vw)} {html.escape(vh)}">']
    for node in root:
        if not node.tag.endswith("path"):
            continue
        d = node.attrib.get(ns + "pathData")
        if not d:
            continue
        fill = node.attrib.get(ns + "fillColor", "#FFFFFF")
        fill_type = node.attrib.get(ns + "fillType")
        fill_rule = ' fill-rule="evenodd"' if fill_type == "evenOdd" else ""
        parts.append(f'<path d="{html.escape(d, quote=True)}" fill="{html.escape(fill, quote=True)}"{fill_rule}/>')
    parts.append("</svg>\n")
    return "".join(parts).encode("utf-8")


def provenance(slug: str, path: Path, **kwargs) -> dict:
    data = path.read_bytes()
    return {
        "slug": slug,
        "local_master": path.relative_to(ROOT).as_posix(),
        "local_sha256": sha256(data),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }


def sync_telegram() -> dict:
    source = f"https://raw.githubusercontent.com/DrKLO/Telegram/{TELEGRAM_COMMIT}/TMessagesProj/src/main/res/drawable/icon_plane.xml"
    raw, resolved, content_type = fetch(source)
    path = save_bytes("telegram", ".svg", android_vector_to_svg(raw))
    return provenance("telegram", path, official_source="DrKLO/Telegram production Android VectorDrawable", source_url=source, resolved_asset_url=resolved, source_type="official Android VectorDrawable", source_version=TELEGRAM_COMMIT, original_format="Android VectorDrawable XML", conversion="lossless pathData/XML -> SVG wrapper; path geometry unchanged", geometry_modifications="NONE", original_sha256=sha256(raw), fetched_content_type=content_type)


def sync_github() -> dict:
    source = f"https://raw.githubusercontent.com/primer/octicons/{OCTICONS_COMMIT}/icons/mark-github-24.svg"
    raw, resolved, content_type = fetch(source)
    path = save_bytes("github", ".svg", raw)
    return provenance("github", path, official_source="GitHub Primer Octicons — mark-github-24.svg", source_url=source, resolved_asset_url=resolved, source_type="official GitHub-owned SVG", source_version=OCTICONS_COMMIT, original_format="SVG", conversion="NONE; exact upstream SVG bytes", geometry_modifications="NONE", original_sha256=sha256(raw), fetched_content_type=content_type)


def sync_revanced() -> dict:
    source = f"https://raw.githubusercontent.com/ReVanced/revanced-branding/{REVANCED_COMMIT}/assets/revanced-logo/revanced-logo.svg"
    raw, resolved, content_type = fetch(source)
    path = save_bytes("revanced", ".svg", raw)
    return provenance("revanced", path, official_source="ReVanced/revanced-branding official ReVanced logo", source_url=source, resolved_asset_url=resolved, source_type="official project SVG", source_version=REVANCED_COMMIT, original_format="SVG", conversion="NONE; exact upstream SVG bytes", geometry_modifications="NONE", original_sha256=sha256(raw), fetched_content_type=content_type, note="Brand artwork remains subject to upstream ReVanced branding/permission terms; not relicensed by lmao-glass.")


def play_icon(slug: str, page: str) -> dict:
    page_data, page_resolved, _ = fetch(page)
    parser = parse_html(page_data)
    candidates = list(dict.fromkeys([urllib.parse.urljoin(page_resolved, c) for c in parser.icon_images + parser.meta_images]))
    if not candidates:
        text = page_data.decode("utf-8", errors="replace")
        candidates = [html.unescape(c) for c in re.findall(r'https://play-lh\.googleusercontent\.com/[^"\\s&<]+', text)]
    errors = []
    for candidate in candidates:
        if "play-lh.googleusercontent.com" not in urllib.parse.urlparse(candidate).netloc:
            continue
        try:
            asset, resolved, content_type = fetch(candidate)
            image = Image.open(io.BytesIO(asset))
            if min(image.size) < 128:
                continue
            path = save_png(slug, asset)
            return provenance(slug, path, official_source="Google Play developer-published app icon", source_url=page, resolved_asset_url=resolved, source_type="official current launcher/app-listing raster fallback", source_version="live Google Play listing at build time", original_format=(image.format or content_type or "raster"), conversion="lossless decode/re-encode to RGBA PNG; no trace/crop/recolor", geometry_modifications="NONE", original_sha256=sha256(asset), fetched_content_type=content_type, source_page_sha256=sha256(page_data), note="Used only where a deterministic current official app icon vector is not available to this build pipeline.")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError(f"{slug}: failed to download a usable official Play icon: {'; '.join(errors[:4])}")


def google_play_prism() -> dict:
    pages = [
        "https://developer.android.com/google/play/billing/alternative/interim-ux/user-choice",
        "https://developer.android.com/google/play/billing/alternative/interim-ux/billing-choice",
        "https://partnermarketinghub.withgoogle.com/brands/google-play/google-play/lockups-icons-badges/?folder=86641",
    ]
    errors = []
    for page in pages:
        try:
            page_data, resolved_page, _ = fetch(page)
            parser = parse_html(page_data)
            target_links = [(href, text) for href, text in parser.links if "google play prism" in text.lower() or ("prism" in text.lower() and "play" in text.lower())]
            text = page_data.decode("utf-8", errors="replace")
            direct = re.findall(r'https?://[^"\'<>\\s]+(?:google[-_ ]?play|play)[^"\'<>\\s]+(?:prism|icon)[^"\'<>\\s]+', text, flags=re.IGNORECASE)
            urls = [urllib.parse.urljoin(resolved_page, href) for href, _ in target_links] + direct
            for url in dict.fromkeys(urls):
                try:
                    raw, resolved, content_type = fetch(html.unescape(url))
                    suffix = Path(urllib.parse.urlparse(resolved).path).suffix.lower()
                    if content_type == "image/svg+xml" or suffix == ".svg" or raw.lstrip().startswith(b"<svg"):
                        path = save_bytes("google_play", ".svg", raw)
                        return provenance("google_play", path, official_source="Google Android Developers / Google Play prism asset", source_url=page, resolved_asset_url=resolved, source_type="official Google Play prism vector", source_version="live official Google page at build time", original_format="SVG", conversion="NONE; exact downloaded vector", geometry_modifications="NONE", original_sha256=sha256(raw), fetched_content_type=content_type)
                    try:
                        image = Image.open(io.BytesIO(raw))
                        if min(image.size) >= 24:
                            path = save_png("google_play", raw)
                            return provenance("google_play", path, official_source="Google Android Developers / Google Play prism asset", source_url=page, resolved_asset_url=resolved, source_type="official Google Play prism image", source_version="live official Google page at build time", original_format=image.format or content_type, conversion="lossless decode/re-encode to RGBA PNG", geometry_modifications="NONE", original_sha256=sha256(raw), fetched_content_type=content_type)
                    except Exception:
                        pass
                except Exception as exc:
                    errors.append(f"asset {url}: {exc}")
        except Exception as exc:
            errors.append(f"page {page}: {exc}")
    raise RuntimeError("google_play: official prism asset could not be resolved automatically: " + "; ".join(errors[:6]))


def main() -> None:
    for p in OUT.iterdir():
        if p.is_file() and p.name != "README.md":
            p.unlink()
    records = {
        "telegram": sync_telegram(),
        "github": sync_github(),
        "revanced": sync_revanced(),
    }
    for slug, page in PLAY_PAGES.items():
        records[slug] = play_icon(slug, page)
    records["google_play"] = google_play_prism()
    required = {"telegram", "discord", "github", "google_play", "pinterest", "kaspi", "2gis", "revanced", "gamehub"}
    if set(records) != required:
        raise RuntimeError(f"source set mismatch: got {sorted(records)}")
    (OUT / "provenance.json").write_text(json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("official source sync:", ", ".join(sorted(records)))


if __name__ == "__main__":
    main()
