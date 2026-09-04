from __future__ import annotations

import io
import json
import math
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
MASTER = 1024
DP_SCALE = MASTER / 108.0
OFFICIAL = ROOT / "artwork" / "official"


def rounded_mask(n: int = MASTER, margin: int = 62, radius: int = 236) -> np.ndarray:
    im = Image.new("L", (n, n), 0)
    ImageDraw.Draw(im).rounded_rectangle((margin, margin, n - margin, n - margin), radius=radius, fill=255)
    return np.asarray(im, dtype=np.float32) / 255.0


def artwork_path(slug: str) -> Path:
    for suffix in (".svg", ".png", ".webp", ".jpg", ".jpeg"):
        p = OFFICIAL / f"{slug}{suffix}"
        if p.exists():
            return p
    raise FileNotFoundError(f"official artwork missing for {slug}; run a source-sync script first")


def load_artwork(path: Path) -> Image.Image:
    if path.suffix.lower() == ".svg":
        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=MASTER, output_height=MASTER)
        return Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.open(path).convert("RGBA")


def render_artwork(path: Path, scale: float, ox: float, oy: float) -> Image.Image:
    """Place source artwork optically without changing source geometry."""
    im = load_artwork(path)
    a = np.asarray(im)[..., 3]
    ys, xs = np.where(a > 4)
    if len(xs) == 0:
        return im
    crop = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    target = int(MASTER * 0.52 * scale / 0.75)
    ratio = min(target / crop.width, target / crop.height)
    crop = crop.resize(
        (max(1, int(crop.width * ratio)), max(1, int(crop.height * ratio))),
        Image.Resampling.LANCZOS,
    )
    out = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    x = int((MASTER - crop.width) / 2 + ox * MASTER)
    y = int((MASTER - crop.height) / 2 + oy * MASTER)
    out.alpha_composite(crop, (x, y))
    return out


def extracted_logo_mask(glyph: Image.Image) -> np.ndarray:
    """Return geometry only, never brand colour.

    Transparent/vector sources contribute their authored alpha. A fully opaque
    raster is contrast-separated only as an explicitly temporary fallback; the
    calibration validator can reject such provenance for production baselines.
    """
    arr = np.asarray(glyph, dtype=np.float32) / 255.0
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    opaque_coverage = float(np.mean(alpha > 0.97))

    if opaque_coverage < 0.58:
        return np.clip(alpha, 0, 1)

    pad = max(8, MASTER // 24)
    border = np.concatenate(
        [
            rgb[:pad].reshape(-1, 3),
            rgb[-pad:].reshape(-1, 3),
            rgb[:, :pad].reshape(-1, 3),
            rgb[:, -pad:].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border, axis=0)
    border_delta = np.sqrt(np.mean((rgb - bg[None, None, :]) ** 2, axis=2))
    blurred = np.asarray(
        Image.fromarray((rgb * 255).astype("uint8"), "RGB").filter(ImageFilter.GaussianBlur(radius=MASTER * 0.045)),
        dtype=np.float32,
    ) / 255.0
    local_delta = np.sqrt(np.mean((rgb - blurred) ** 2, axis=2))
    signal = np.maximum(border_delta * 0.78, local_delta * 2.0)
    mask = np.clip((signal - 0.055) / 0.22, 0, 1)
    mask = ndimage.gaussian_filter(mask, sigma=1.2)
    mask = np.clip(mask * alpha, 0, 1)
    if float(mask.mean()) > 0.72:
        mask = np.clip(local_delta * 5.0, 0, 1) * alpha
    return mask


def lens_fields(mask: np.ndarray, band_px: float, z: float):
    """Build a rounded transparent slab from a mask.

    Height is zero at the boundary and rises into the body. This is the opposite
    of the older edge-raised approximation and gives a physically sensible
    normal field for a lens/slab edge.
    """
    m = np.clip(mask.astype(np.float32), 0, 1)
    binary = m > 0.08
    inside = ndimage.distance_transform_edt(binary)
    t = np.clip(inside / max(1.0, band_px), 0, 1)
    edge = (1.0 - t) * m
    height = (np.sin(t * math.pi * 0.5) ** 0.72) * m
    gy, gx = np.gradient(height)
    nz0 = np.full_like(gx, z)
    norm = np.sqrt(gx * gx + gy * gy + nz0 * nz0) + 1e-6
    nx = -gx / norm
    ny = -gy / norm
    nz = nz0 / norm
    return edge, height, nx, ny, nz


def _alpha_union(*layers: np.ndarray) -> np.ndarray:
    out = np.zeros_like(layers[0], dtype=np.float32)
    for layer in layers:
        a = np.clip(layer, 0, 1)
        out = out + a * (1.0 - out)
    return np.clip(out, 0, 1)


def _rgba_layer(rgb, alpha: np.ndarray) -> Image.Image:
    if isinstance(rgb, tuple):
        arr = np.empty((*alpha.shape, 4), dtype=np.uint8)
        arr[..., 0] = rgb[0]
        arr[..., 1] = rgb[1]
        arr[..., 2] = rgb[2]
        arr[..., 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGBA")
    rgb_arr = np.clip(rgb, 0, 1)
    return Image.fromarray(
        (np.dstack([rgb_arr, np.clip(alpha, 0, 1)]) * 255.0).astype(np.uint8),
        "RGBA",
    )


def optical_layers(mask: np.ndarray, edge: np.ndarray, nx: np.ndarray, ny: np.ndarray, nz: np.ndarray, preset: dict, *, glyph: bool):
    """Return neutral optical overlays for one clear-glass body.

    No backdrop or environment colour is baked. The final PNG contains only
    low-alpha neutral body transmission cues plus directional bright/dark edge
    response. Real wallpaper colour therefore passes through the icon alpha.
    """
    ang = math.radians(preset["highlightAngleDeg"])
    lx, ly = math.cos(ang), math.sin(ang)
    side = nx * lx + ny * ly
    lit = np.clip(side, 0, 1)
    dark = np.clip(-side, 0, 1)
    fresnel = ((1.0 - np.clip(nz, 0, 1)) ** 1.7) * edge

    if glyph:
        body_alpha = preset.get("glyphGlassAlpha", 0.024) * mask
        rim_strength = preset.get("glyphRimAlpha", 0.36)
        dark_strength = preset.get("glyphDarkRimAlpha", 0.105)
        spec_strength = preset.get("glyphSpecular", 0.46)
        fresnel_strength = preset.get("glyphFresnelAlpha", 0.075)
        max_alpha = preset.get("glyphMaxAlpha", 0.34)
    else:
        body_alpha = preset.get("glassAlpha", 0.018) * mask
        rim_strength = preset.get("rimAlpha", 0.27)
        dark_strength = preset.get("darkRimAlpha", 0.082)
        spec_strength = preset.get("specular", 0.40)
        fresnel_strength = preset.get("fresnelAlpha", 0.060)
        max_alpha = preset.get("maxAlpha", 0.28)

    # A broad neutral reflection is weaker than the narrow edge/specular lobe.
    broad_reflection = (lit ** 1.6) * (edge ** 1.25) * rim_strength * 0.28
    bright_rim = (0.28 + 0.72 * lit) * (edge ** 1.65) * rim_strength
    specular = (lit ** (3.0 + 15.0 * preset.get("roughness", 0.18))) * edge * spec_strength
    dark_rim = (0.22 + 0.78 * dark) * (edge ** 1.52) * dark_strength
    fresnel_alpha = fresnel * fresnel_strength

    # Mild curvature/caustic cue: paired neutral lobe, not a sampled backdrop.
    normal_xy = np.sqrt(nx * nx + ny * ny)
    caustic = normal_xy * edge * (0.20 + 0.80 * lit) * preset.get("causticAlpha", 0.035)

    bright_alpha = np.clip(broad_reflection + bright_rim * 0.58 + specular * 0.32 + fresnel_alpha + caustic, 0, max_alpha)
    dark_alpha = np.clip(dark_rim, 0, max_alpha * 0.55)
    body_alpha = np.clip(body_alpha, 0, max_alpha * 0.35)
    combined = _alpha_union(body_alpha, bright_alpha, dark_alpha)

    return {
        "body": body_alpha,
        "bright": bright_alpha,
        "dark": dark_alpha,
        "combined": combined,
        "fresnel": fresnel,
        "lit": lit,
        "opposite": dark,
    }


def render_one_debug(slug: str, cfg: dict, preset: dict):
    n = MASTER
    outer_mask = rounded_mask(n)
    outer_edge, height, nx, ny, nz = lens_fields(
        outer_mask,
        preset["refractionBandDp"] * DP_SCALE,
        z=preset.get("outerNormalZ", 0.56),
    )
    outer = optical_layers(outer_mask, outer_edge, nx, ny, nz, preset, glyph=False)

    base = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    # Body is nearly invisible; edge polarity creates the glass boundary.
    base.alpha_composite(_rgba_layer((232, 234, 236), outer["body"]))
    base.alpha_composite(_rgba_layer((17, 18, 20), outer["dark"]))
    base.alpha_composite(_rgba_layer((255, 255, 255), outer["bright"]))

    glyph = render_artwork(artwork_path(slug), cfg["scale"], cfg["offsetX"], cfg["offsetY"])
    glyph_mask = extracted_logo_mask(glyph)
    glyph_edge, glyph_height, gnx, gny, gnz = lens_fields(
        glyph_mask,
        preset.get("glyphRefractionBandDp", 3.8) * DP_SCALE,
        z=preset.get("glyphNormalZ", 0.40),
    )
    inner = optical_layers(glyph_mask, glyph_edge, gnx, gny, gnz, preset, glyph=True)

    # Sub-percent neutral occlusion only to separate two transparent bodies.
    contact_alpha = np.clip(
        ndimage.gaussian_filter(glyph_mask, sigma=preset.get("contactBlurPx", 8.0))
        * preset.get("contactAlpha", 0.008),
        0,
        0.02,
    )
    base.alpha_composite(_rgba_layer((8, 9, 10), contact_alpha))
    base.alpha_composite(_rgba_layer((234, 236, 238), inner["body"]))
    base.alpha_composite(_rgba_layer((12, 13, 15), inner["dark"]))
    base.alpha_composite(_rgba_layer((255, 255, 255), inner["bright"]))

    normal = np.dstack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)])
    debug = {
        "outer_mask": outer_mask,
        "outer_edge": outer_edge,
        "outer_alpha": outer["combined"],
        "glyph_mask": glyph_mask,
        "glyph_edge": glyph_edge,
        "glyph_alpha": inner["combined"],
        "glyph_height": glyph_height,
    }
    return base, outer_mask, height, normal, debug


def render_one(slug: str, cfg: dict, preset: dict):
    im, mask, height, normal, _ = render_one_debug(slug, cfg, preset)
    return im, mask, height, normal


def save_maps(slug: str, mask: np.ndarray, height: np.ndarray, normal: np.ndarray):
    Image.fromarray((mask * 255).astype("uint8")).save(ROOT / f"artwork/masks/{slug}.png")
    Image.fromarray((height * 65535).astype("uint16")).save(ROOT / f"artwork/height/{slug}.png")
    Image.fromarray((normal * 255).astype("uint8"), "RGB").save(ROOT / f"artwork/normals/{slug}.png")


def backgrounds(size: int):
    bg = []
    for name, color in [
        ("white", (245, 245, 245)),
        ("black", (14, 14, 16)),
        ("gray", (120, 124, 130)),
        ("warm", (151, 118, 92)),
    ]:
        bg.append((name, Image.new("RGB", (size, size), color)))
    a = np.zeros((size, size, 3), np.uint8)
    y, x = np.mgrid[0:size, 0:size]
    a[..., 0] = (70 + 60 * np.sin(x / 17) + 30 * np.cos(y / 29)).clip(0, 255)
    a[..., 1] = (80 + 55 * np.sin((x + y) / 31) + 25 * np.cos(x / 13)).clip(0, 255)
    a[..., 2] = (110 + 70 * np.cos(y / 21) + 25 * np.sin(x / 9)).clip(0, 255)
    bg.append(("complex", Image.fromarray(a)))
    return bg


def contact_sheet(outputs: dict, cfgs: dict):
    cell = 190
    icon = 130
    labels = 34
    bgs = backgrounds(icon)
    cols = len(bgs)
    rows = len(outputs)
    sheet = Image.new("RGB", (cell * cols, rows * (cell + labels)), (232, 232, 234))
    draw = ImageDraw.Draw(sheet)
    for r, (slug, im) in enumerate(outputs.items()):
        small = im.resize((icon, icon), Image.Resampling.LANCZOS)
        for c, (bn, bg) in enumerate(bgs):
            canvas = bg.copy().convert("RGBA")
            canvas.alpha_composite(small)
            x = c * cell + (cell - icon) // 2
            y = r * (cell + labels) + 8
            sheet.paste(canvas.convert("RGB"), (x, y))
            draw.text((c * cell + 8, y + icon + 4), bn, fill=(40, 40, 42))
        draw.text((8, r * (cell + labels) + 2), cfgs[slug]["displayName"], fill=(20, 20, 22))
    sheet.save(ROOT / "generated/contact-sheets/qa-grid.png")


def source_geometry_sheet(outputs: dict, cfgs: dict):
    cell_w = 360
    cell_h = 260
    icon = 188
    sheet = Image.new("RGB", (cell_w * 2, cell_h * len(outputs)), (232, 232, 234))
    draw = ImageDraw.Draw(sheet)
    for r, (slug, rendered) in enumerate(outputs.items()):
        source = render_artwork(
            artwork_path(slug), cfgs[slug]["scale"], cfgs[slug]["offsetX"], cfgs[slug]["offsetY"]
        )
        source_mask = extracted_logo_mask(source)
        mask_preview = Image.fromarray((source_mask * 255).astype("uint8"), "L").convert("RGBA")
        mask_preview.putalpha(Image.fromarray((source_mask * 255).astype("uint8"), "L"))
        source_small = mask_preview.resize((icon, icon), Image.Resampling.LANCZOS)
        out = rendered.resize((icon, icon), Image.Resampling.LANCZOS)
        for c, (label, im) in enumerate(
            (("official geometry mask", source_small), ("colorless glass-in-glass render", out))
        ):
            x = c * cell_w + (cell_w - icon) // 2
            y = r * cell_h + 42
            canvas = Image.new("RGBA", (icon, icon), (118, 122, 128, 255))
            canvas.alpha_composite(im)
            sheet.paste(canvas.convert("RGB"), (x, y))
            draw.text((c * cell_w + 12, r * cell_h + 10), label, fill=(30, 30, 32))
        draw.text((12, r * cell_h + 224), cfgs[slug]["displayName"], fill=(20, 20, 22))
    sheet.save(ROOT / "generated/contact-sheets/source-geometry.png")


def android_xml(slug: str):
    v26 = f'''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_{slug}_background" />
    <foreground android:drawable="@drawable/ic_{slug}_foreground" />
</adaptive-icon>
'''
    v33 = f'''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_{slug}_background" />
    <foreground android:drawable="@drawable/ic_{slug}_foreground" />
    <monochrome android:drawable="@drawable/ic_{slug}_monochrome" />
</adaptive-icon>
'''
    (ROOT / f"android-pack/src/main/res/mipmap-anydpi-v26/ic_{slug}.xml").write_text(v26)
    (ROOT / f"android-pack/src/main/res/mipmap-anydpi-v33/ic_{slug}.xml").write_text(v33)
    (ROOT / f"android-pack/src/main/res/drawable/ic_{slug}_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">'
        '<solid android:color="#00000000"/></shape>\n'
    )


def ensure_output_dirs():
    for d in [
        ROOT / "android-pack/src/main/res/drawable",
        ROOT / "android-pack/src/main/res/mipmap-anydpi-v26",
        ROOT / "android-pack/src/main/res/mipmap-anydpi-v33",
        ROOT / "android-pack/src/main/assets",
        ROOT / "generated/icons",
        ROOT / "generated/contact-sheets",
        ROOT / "variants/regular",
        ROOT / "artwork/masks",
        ROOT / "artwork/height",
        ROOT / "artwork/normals",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def main():
    ensure_output_dirs()
    cfgs = json.loads((ROOT / "android-pack/launcher-mappings/icons.json").read_text())
    presets = json.loads((ROOT / "renderer/material-presets.json").read_text())
    preset = presets["liquid_regular"]
    outs = {}

    for slug, cfg in cfgs.items():
        im, mask, height, normal = render_one(slug, cfg, preset)
        outs[slug] = im
        im.save(ROOT / f"generated/icons/{slug}_1024.png")
        im.resize((512, 512), Image.Resampling.LANCZOS).save(ROOT / f"variants/regular/{slug}.png")
        save_maps(slug, mask, height, normal)
        android_xml(slug)

        im.resize((432, 432), Image.Resampling.LANCZOS).save(
            ROOT / f"android-pack/src/main/res/drawable/ic_{slug}_foreground.png"
        )
        glyph = render_artwork(artwork_path(slug), cfg["scale"], cfg["offsetX"], cfg["offsetY"])
        logo_mask = extracted_logo_mask(glyph)
        # Android themed-icons compatibility only. Normal pack rendering never
        # consumes this monochrome asset.
        mono = Image.new("RGBA", (MASTER, MASTER), (255, 255, 255, 0))
        mono.putalpha(Image.fromarray((logo_mask * 255).astype("uint8"), "L"))
        mono.resize((432, 432), Image.Resampling.LANCZOS).save(
            ROOT / f"android-pack/src/main/res/drawable/ic_{slug}_monochrome.png"
        )

    contact_sheet(outs, cfgs)
    source_geometry_sheet(outs, cfgs)
    print("generated", len(outs), "neutral transparent glass-in-glass icons")


if __name__ == "__main__":
    main()
