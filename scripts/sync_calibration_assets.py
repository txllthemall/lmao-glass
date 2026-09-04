from __future__ import annotations

import html
import importlib.util
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
source_file = Path(__file__).with_name("sync_official_assets.py")
spec = importlib.util.spec_from_file_location("sync_official_assets", source_file)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {source_file}")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

OUT = sync.OUT
DISCORD_BRAND = "https://discord.com/branding"


class BrandImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        urls: list[str] = []
        for key in ("src", "data-src"):
            if a.get(key):
                urls.append(a[key])
        for key in ("srcset", "data-srcset"):
            if a.get(key):
                for part in a[key].split(","):
                    candidate = part.strip().split(" ", 1)[0]
                    if candidate:
                        urls.append(candidate)
        for url in urls:
            self.images.append(
                {
                    "url": html.unescape(url),
                    "alt": a.get("alt", ""),
                    "title": a.get("title", ""),
                    "class": a.get("class", ""),
                }
            )


def _candidate_score(rec: dict[str, str]) -> int:
    text = " ".join((rec.get("alt", ""), rec.get("title", ""), rec.get("url", ""))).lower()
    score = 0
    for token, points in (
        ("symbol", 18),
        ("clyde", 18),
        ("discord", 8),
        ("logo", 5),
        ("mark", 3),
    ):
        if token in text:
            score += points
    for token, points in (("wordmark", 18), ("banner", 12), ("clearspace", 8), ("lockup", 7), ("header", 6)):
        if token in text:
            score -= points
    lower = rec.get("url", "").lower()
    if lower.endswith(".svg"):
        score += 10
    elif lower.endswith((".png", ".webp")):
        score += 4
    return score


def _transparent_raster(data: bytes):
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    if min(image.size) < 64:
        return None
    w, h = image.size
    aspect = w / max(1, h)
    if not 0.55 <= aspect <= 1.85:
        return None
    hist = image.getchannel("A").histogram()
    total = sum(hist)
    transparent = sum(hist[:250]) / max(1, total)
    visible = sum(hist[8:]) / max(1, total)
    if transparent < 0.035 or visible < 0.05:
        return None
    return image, transparent


def sync_discord_symbol() -> dict:
    page_data, page_resolved, _ = sync.fetch(DISCORD_BRAND)
    parser = BrandImageParser()
    parser.feed(page_data.decode("utf-8", errors="replace"))

    # Webflow can also embed asset URLs outside <img> tags. Keep those as a
    # lower-priority fallback while remaining on Discord's official page/CDN.
    raw_text = page_data.decode("utf-8", errors="replace")
    direct = re.findall(
        r'https://cdn\.prod\.website-files\.com/[^"\'<>\\s]+?(?:\.svg|\.png|\.webp)(?:\?[^"\'<>\\s]*)?',
        raw_text,
        flags=re.IGNORECASE,
    )
    seen = {r["url"] for r in parser.images}
    for url in direct:
        url = html.unescape(url)
        if url not in seen:
            parser.images.append({"url": url, "alt": "", "title": "", "class": ""})
            seen.add(url)

    candidates = sorted(parser.images, key=_candidate_score, reverse=True)
    errors: list[str] = []
    best = None

    for rec in candidates[:80]:
        url = rec["url"]
        if not url.startswith("https://"):
            continue
        host = re.sub(r"^https://([^/]+)/.*$", r"\1", url)
        if host not in {"cdn.prod.website-files.com", "discord.com", "www.discord.com"}:
            continue
        try:
            data, resolved, content_type = sync.fetch(url)
            suffix = Path(resolved.split("?", 1)[0]).suffix.lower()
            score = _candidate_score(rec)
            if content_type == "image/svg+xml" or suffix == ".svg" or data.lstrip().startswith(b"<svg"):
                # Reject obvious horizontal wordmarks by viewBox/width if parseable.
                text = data.decode("utf-8", errors="ignore")[:4000]
                m = re.search(r'viewBox=["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', text, re.I)
                if m:
                    aspect = float(m.group(1)) / max(1e-6, float(m.group(2)))
                    if not 0.55 <= aspect <= 1.85:
                        continue
                score += 30
                if best is None or score > best[0]:
                    best = (score, "svg", data, resolved, content_type, rec)
                continue

            raster = _transparent_raster(data)
            if raster is None:
                continue
            image, transparent = raster
            score += int(transparent * 12)
            if best is None or score > best[0]:
                best = (score, "png", data, resolved, content_type, rec)
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    if best is None:
        preview = [f"{_candidate_score(r)}:{r.get('alt','')}:{r.get('url','')}" for r in candidates[:12]]
        raise RuntimeError(
            "discord: no transparent official Symbol/Clyde asset resolved from discord.com/branding; "
            + "candidates=" + " | ".join(preview)
            + ("; errors=" + "; ".join(errors[:6]) if errors else "")
        )

    _, kind, data, resolved, content_type, rec = best
    if kind == "svg":
        path = sync.save_bytes("discord", ".svg", data)
        original_format = "SVG"
        conversion = "NONE; exact official Discord CDN vector bytes"
    else:
        path = sync.save_png("discord", data)
        original_format = Image.open(io.BytesIO(data)).format or content_type or "raster"
        conversion = "lossless decode/re-encode to RGBA PNG; geometry not traced or redrawn"

    return sync.provenance(
        "discord",
        path,
        official_source="Discord official Brand Assets — Symbol/Clyde",
        source_url=DISCORD_BRAND,
        resolved_asset_url=resolved,
        source_type="official Discord brand symbol asset",
        source_version="live Discord Brand Assets page at build time",
        original_format=original_format,
        conversion=conversion,
        geometry_modifications="NONE",
        original_sha256=sync.sha256(data),
        fetched_content_type=content_type,
        source_page_sha256=sync.sha256(page_data),
        source_alt=rec.get("alt", ""),
        note="Used as geometry only by the glass renderer; source RGB/brand colour is discarded.",
    )


def main() -> None:
    for p in OUT.iterdir():
        if p.is_file() and p.name != "README.md":
            p.unlink()

    records = {
        "telegram": sync.sync_telegram(),
        "github": sync.sync_github(),
        "discord": sync_discord_symbol(),
    }
    (OUT / "provenance.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("calibration official source sync:", ", ".join(sorted(records)))


if __name__ == "__main__":
    main()
