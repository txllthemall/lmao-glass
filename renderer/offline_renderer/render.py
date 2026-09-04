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


def hexrgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def rounded_mask(n: int = MASTER, margin: int = 62, radius: int = 236) -> np.ndarray:
    im = Image.new("L", (n, n), 0)
    ImageDraw.Draw(im).rounded_rectangle((margin, margin, n - margin, n - margin), radius=radius, fill=255)
    return np.asarray(im, dtype=np.float32) / 255.0


def sample_bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.stack(
        [ndimage.map_coordinates(img[..., c], [y, x], order=1, mode="nearest") for c in range(img.shape[2])],
        axis=-1,
    )


def virtual_environment(n: int, tint: np.ndarray) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    u = x / (n - 1)
    v = y / (n - 1)
    base = np.zeros((n, n, 3), np.float32)
    base[..., 0] = 0.50 + 0.08 * (1 - v) + 0.03 * np.sin((u + v) * math.pi * 2)
    base[..., 1] = 0.52 + 0.07 * (1 - v) + 0.02 * np.cos(u * math.pi * 2)
    base[..., 2] = 0.56 + 0.08 * (1 - v)
    spill = np.exp(-(((u - 0.20) / 0.30) ** 2 + ((v - 0.18) / 0.28) ** 2))[..., None]
    return np.clip(base * (1 - spill * 0.04) + tint[None, None, :] * (spill * 0.04), 0, 1)


def artwork_path(slug: str) -> Path:
    for suffix in (".svg", ".png", ".webp", ".jpg", ".jpeg"):
        p = OFFICIAL / f"{slug}{suffix}"
        if p.exists():
            return p
    raise FileNotFoundError(f"official artwork missing for {slug}; run scripts/sync_official_assets.py first")


def load_artwork(path: Path) -> Image.Image:
    if path.suffix.lower() == ".svg":
        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=MASTER, output_height=MASTER)
        return Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.open(path).convert("RGBA")


def render_artwork(path: Path, scale: float, ox: float, oy: float) -> Image.Image:
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
    """Return foreground geometry without preserving an opaque app-icon square.

    Vector/transparent assets keep their authored alpha. Fully opaque Play Store
    rasters are converted to a contrast-derived foreground mask so the result is
    glass, not an opaque icon pasted inside a glass tile.
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

    # A pathological flat raster should not become a solid translucent square.
    if float(mask.mean()) > 0.72:
        mask = np.clip(local_delta * 5.0, 0, 1) * alpha
    return mask


def render_one(slug: str, cfg: dict, preset: dict):
    n = MASTER
    mask = rounded_mask(n)
    inside = ndimage.distance_transform_edt(mask > 0.5)
    band = max(1, preset["refractionBandDp"] * DP_SCALE)
    edge = np.clip(1.0 - inside / band, 0, 1)
    height = (1 - np.sqrt(np.clip(1 - edge * edge, 0, 1))) * mask

    gy, gx = np.gradient(height)
    nz = np.full_like(gx, 0.62)
    norm = np.sqrt(gx * gx + gy * gy + nz * nz) + 1e-6
    nx = -gx / norm
    ny = -gy / norm
    nz = nz / norm

    tint = hexrgb(cfg["tint"])
    env = virtual_environment(n, tint)
    env_img = Image.fromarray((env * 255).astype("uint8")).filter(
        ImageFilter.GaussianBlur(radius=preset["blurDp"] * DP_SCALE)
    )
    env = np.asarray(env_img, dtype=np.float32) / 255.0

    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    refr_px = preset["refractionDp"] * DP_SCALE
    sx = x + nx * refr_px * (0.18 + 0.82 * edge)
    sy = y + ny * refr_px * (0.18 + 0.82 * edge)
    refr = sample_bilinear(env, sx, sy)

    ang = math.radians(preset["highlightAngleDeg"])
    lx, ly = math.cos(ang), math.sin(ang)
    ndl_raw = nx * lx + ny * ly
    ndl = np.clip(ndl_raw, 0, 1)
    opposite = np.clip(-ndl_raw, 0, 1)
    fresnel = (1 - np.clip(nz, 0, 1)) ** 1.55 * edge

    disp_edge = edge * (ndl ** 2)
    disp = preset["dispersionDp"] * DP_SCALE
    refr[..., 0] = sample_bilinear(env, sx + nx * disp * disp_edge, sy + ny * disp * disp_edge)[..., 0]
    refr[..., 2] = sample_bilinear(env, sx - nx * disp * disp_edge, sy - ny * disp * disp_edge)[..., 2]

    # Clear glass: almost no body opacity. Identity comes from optical edge
    # behavior, not from a milky translucent fill.
    spec = (ndl ** (3.2 + 14 * preset["roughness"])) * edge * preset["specular"]
    rim = (edge ** 1.55) * preset["rimAlpha"]
    body_alpha = preset["glassAlpha"] * mask
    out_a = np.clip(body_alpha + rim * 0.42 + spec * 0.30 + fresnel * 0.15, 0, 0.44) * mask

    rgb = refr * (0.965 + 0.035 * tint[None, None, :])
    rgb += tint[None, None, :] * (0.022 * edge[..., None])
    rgb += spec[..., None] * 0.62 + fresnel[..., None] * 0.16
    rgb -= opposite[..., None] * edge[..., None] * 0.055

    shadow = ndimage.gaussian_filter(edge, preset["shadowBlurDp"] * DP_SCALE) * preset["shadowAlpha"]
    rgb -= shadow[..., None] * 0.018
    rng = np.random.default_rng(20260904)
    rgb += rng.normal(0, preset["noise"], (n, n, 1)).astype(np.float32) * mask[..., None]
    rgb = np.clip(rgb, 0, 1)

    base = Image.fromarray((np.dstack([rgb, out_a]) * 255).astype("uint8"), "RGBA")

    # The brand artwork itself is also glass. Opaque raster backgrounds are
    # stripped into a foreground mask and then rendered as stained/clear glass.
    glyph = render_artwork(artwork_path(slug), cfg["scale"], cfg["offsetX"], cfg["offsetY"])
    g = np.asarray(glyph, dtype=np.float32) / 255.0
    logo_mask = extracted_logo_mask(glyph)
    logo_edge = np.clip(ndimage.gaussian_gradient_magnitude(logo_mask, sigma=1.15) * 4.0, 0, 1)
    logo_spec = np.clip(ndl * logo_edge, 0, 1)

    source_rgb = g[..., :3]
    glass_rgb = np.clip(source_rgb * 0.34 + refr * 0.54 + tint[None, None, :] * 0.12, 0, 1)
    glass_rgb += logo_spec[..., None] * 0.32
    glass_rgb = np.clip(glass_rgb, 0, 1)

    glyph_opacity = preset["glyphOpacity"]
    glyph_alpha = logo_mask * glyph_opacity * (0.34 + 0.48 * logo_edge)
    glyph_alpha += logo_spec * 0.16
    glyph_alpha = np.clip(glyph_alpha, 0, 0.55)

    # Very soft contact shadow only; no sticker-like dark drop shadow.
    soft = Image.fromarray((logo_mask * 255).astype("uint8"), "L").filter(ImageFilter.GaussianBlur(radius=8))
    shadow_rgba = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    shadow_rgba.putalpha(soft.point(lambda p: int(p * 0.025)))
    base.alpha_composite(shadow_rgba, (3, 5))

    glass_glyph = Image.fromarray((np.dstack([glass_rgb, glyph_alpha]) * 255).astype("uint8"), "RGBA")
    base.alpha_composite(glass_glyph)

    return base, mask, height, np.dstack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)])


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
        ("color", (55, 72, 155)),
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
    cols = 5
    rows = len(outputs)
    sheet = Image.new("RGB", (cell * cols, rows * (cell + labels)), (232, 232, 234))
    draw = ImageDraw.Draw(sheet)
    bgs = backgrounds(icon)
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
        ).resize((icon, icon), Image.Resampling.LANCZOS)
        out = rendered.resize((icon, icon), Image.Resampling.LANCZOS)
        for c, (label, im) in enumerate((("official artwork + optical placement", source), ("transparent glass render", out))):
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
        mono = Image.new("RGBA", (MASTER, MASTER), (255, 255, 255, 0))
        mono.putalpha(Image.fromarray((logo_mask * 255).astype("uint8"), "L"))
        mono.resize((432, 432), Image.Resampling.LANCZOS).save(
            ROOT / f"android-pack/src/main/res/drawable/ic_{slug}_monochrome.png"
        )

    contact_sheet(outs, cfgs)
    source_geometry_sheet(outs, cfgs)
    print("generated", len(outs), "transparent glass icons from official source cache")


if __name__ == "__main__":
    main()
