from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TRIO = ("telegram", "github", "discord")
errors: list[str] = []

metrics_path = ROOT / "generated" / "calibration" / "metrics.json"
provenance_path = ROOT / "artwork" / "official" / "provenance.json"
icons_path = ROOT / "android-pack" / "launcher-mappings" / "icons.json"

if not metrics_path.exists():
    errors.append("missing generated/calibration/metrics.json")
    metrics = {}
else:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

if not provenance_path.exists():
    errors.append("missing artwork/official/provenance.json")
    provenance = {}
else:
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

icons = json.loads(icons_path.read_text(encoding="utf-8"))

for slug in TRIO:
    if slug not in icons:
        errors.append(f"{slug}: missing launcher metadata")
        continue
    if "tint" in icons[slug] or "brandColor" in icons[slug]:
        errors.append(f"{slug}: normal rendering metadata must not carry a render tint")

    png = ROOT / "generated" / "calibration" / f"{slug}.png"
    if not png.exists():
        errors.append(f"{slug}: missing calibration PNG")
    else:
        im = Image.open(png).convert("RGBA")
        if im.size != (1024, 1024):
            errors.append(f"{slug}: wrong calibration size {im.size}")
        if im.getchannel("A").getbbox() is None:
            errors.append(f"{slug}: empty alpha")

    rec = provenance.get(slug)
    if not rec:
        errors.append(f"{slug}: missing official-source provenance")
    else:
        if rec.get("geometry_modifications") != "NONE":
            errors.append(f"{slug}: official geometry was modified")
        if not rec.get("source_url") or not rec.get("resolved_asset_url"):
            errors.append(f"{slug}: incomplete source provenance")
        source_type = (rec.get("source_type") or "").lower()
        if slug == "telegram" and "vectordrawable" not in source_type:
            errors.append("telegram: calibration must use official production VectorDrawable geometry")
        if slug == "github" and "github-owned svg" not in source_type:
            errors.append("github: calibration must use GitHub-owned SVG geometry")
        if slug == "discord":
            if "discord brand symbol" not in source_type:
                errors.append("discord: calibration must use official Discord Brand Assets Symbol/Clyde, not a Play icon raster")
            if "play" in source_type:
                errors.append("discord: Play Store full-app raster is forbidden for calibration")

    m = metrics.get(slug)
    if not m:
        errors.append(f"{slug}: missing alpha/color metrics")
        continue

    def check_max(key: str, limit: float):
        value = float(m.get(key, 999.0))
        if value > limit:
            errors.append(f"{slug}: {key}={value:.4f} > {limit:.4f}")

    def check_min(key: str, limit: float):
        value = float(m.get(key, -999.0))
        if value < limit:
            errors.append(f"{slug}: {key}={value:.4f} < {limit:.4f}")

    check_max("outer_center_alpha_median", 0.075)
    check_min("outer_edge_alpha_p90", 0.045)
    check_max("outer_edge_alpha_p90", 0.42)
    check_max("glyph_center_alpha_median", 0.105)
    check_min("glyph_edge_alpha_p90", 0.050)
    check_max("glyph_edge_alpha_p90", 0.48)
    check_max("max_edge_alpha", 0.55)
    check_max("opaque_pixel_fraction", 0.0005)
    check_max("high_alpha_fraction", 0.010)
    check_max("mean_chroma", 0.012)
    check_min("outer_transmission_fraction_alpha_lt_0_12", 0.72)

    glyph_center = float(m.get("glyph_center_alpha_median", 0.0))
    glyph_edge = float(m.get("glyph_edge_alpha_p90", 0.0))
    if glyph_edge < glyph_center + 0.018:
        errors.append(
            f"{slug}: inner glass is reading as a fill, not a lens; glyph edge {glyph_edge:.4f} vs center {glyph_center:.4f}"
        )

for path in (
    ROOT / "generated" / "contact-sheets" / "glass-in-glass-calibration.png",
    ROOT / "generated" / "contact-sheets" / "glass-in-glass-edges.png",
):
    if not path.exists():
        errors.append(f"missing {path.relative_to(ROOT)}")

if errors:
    print("CALIBRATION QA FAILED")
    print("\n".join(f"- {e}" for e in errors))
    sys.exit(1)

print("CALIBRATION QA PASS")
for slug in TRIO:
    print(slug, json.dumps(metrics[slug], sort_keys=True))
