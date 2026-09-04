from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
renderer_file = ROOT / "renderer" / "offline_renderer" / "render.py"
spec = importlib.util.spec_from_file_location("glass_renderer", renderer_file)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {renderer_file}")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

TRIO = ("telegram", "github", "discord")
OUT = ROOT / "generated" / "calibration"
SHEETS = ROOT / "generated" / "contact-sheets"
OUT.mkdir(parents=True, exist_ok=True)
SHEETS.mkdir(parents=True, exist_ok=True)


def checkerboard(size: int, tile: int = 20) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size]
    q = ((x // tile + y // tile) % 2).astype(np.uint8)
    a = np.where(q[..., None] == 0, np.array([214, 216, 220]), np.array([246, 247, 249])).astype(np.uint8)
    return Image.fromarray(a, "RGB")


def warm_wallpaper(size: int) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    u = x / max(1, size - 1)
    v = y / max(1, size - 1)
    arr = np.zeros((size, size, 3), np.float32)
    arr[..., 0] = 0.33 + 0.40 * (1 - v) + 0.08 * np.sin((u + v) * 5.0)
    arr[..., 1] = 0.25 + 0.27 * (1 - v) + 0.05 * np.sin((u * 1.2 + v) * 5.5)
    arr[..., 2] = 0.22 + 0.20 * (1 - v)
    # Soft translucent curved forms similar in frequency, not copied artwork.
    ring = np.abs(np.sqrt((u - 0.23) ** 2 + (v - 0.25) ** 2) - 0.42)
    arr += np.exp(-(ring / 0.025) ** 2)[..., None] * np.array([0.22, 0.18, 0.16])[None, None, :]
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")


def dark_color_wallpaper(size: int) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    u = x / max(1, size - 1)
    v = y / max(1, size - 1)
    arr = np.zeros((size, size, 3), np.float32)
    arr[..., 0] = 0.06 + 0.18 * np.exp(-((u - 0.75) ** 2 + (v - 0.28) ** 2) / 0.08)
    arr[..., 1] = 0.07 + 0.10 * np.exp(-((u - 0.20) ** 2 + (v - 0.72) ** 2) / 0.10)
    arr[..., 2] = 0.12 + 0.35 * np.exp(-((u - 0.55) ** 2 + (v - 0.55) ** 2) / 0.15)
    arr += (0.025 * np.sin((u * 7 + v * 4) * np.pi))[..., None]
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")


def complex_wallpaper(size: int) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    arr = np.zeros((size, size, 3), np.float32)
    arr[..., 0] = 0.36 + 0.22 * np.sin(x / 19.0) + 0.10 * np.cos(y / 31.0)
    arr[..., 1] = 0.34 + 0.18 * np.sin((x + y) / 27.0) + 0.09 * np.cos(x / 13.0)
    arr[..., 2] = 0.43 + 0.25 * np.cos(y / 23.0) + 0.08 * np.sin(x / 9.0)
    block = (((x // 38 + y // 46) % 3) == 0).astype(np.float32)
    arr += block[..., None] * np.array([0.08, -0.03, 0.06])[None, None, :]
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")


def composite(icon: Image.Image, bg: Image.Image) -> Image.Image:
    canvas = bg.convert("RGBA")
    canvas.alpha_composite(icon)
    return canvas.convert("RGB")


def geometry_preview(mask: np.ndarray) -> Image.Image:
    a = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
    out = np.zeros((*a.shape, 3), np.uint8)
    out[:] = (24, 25, 28)
    out[a > 0] = np.stack([a[a > 0], a[a > 0], a[a > 0]], axis=-1)
    return Image.fromarray(out, "RGB")


def metrics_for(icon: Image.Image, debug: dict) -> dict:
    rgba = np.asarray(icon, dtype=np.float32) / 255.0
    alpha = rgba[..., 3]
    rgb = rgba[..., :3]
    om = debug["outer_mask"]
    oe = debug["outer_edge"]
    gm = debug["glyph_mask"]
    ge = debug["glyph_edge"]

    outer_center = (om > 0.65) & (oe < 0.10) & (gm < 0.08)
    outer_edge = (om > 0.10) & (oe > 0.35)
    glyph_center = (gm > 0.55) & (ge < 0.12)
    glyph_edge = (gm > 0.08) & (ge > 0.35)

    def med(zone):
        vals = alpha[zone]
        return float(np.median(vals)) if vals.size else 0.0

    def p90(zone):
        vals = alpha[zone]
        return float(np.percentile(vals, 90)) if vals.size else 0.0

    optical = alpha > 0.008
    if optical.any():
        chroma = np.max(rgb[optical], axis=1) - np.min(rgb[optical], axis=1)
        mean_chroma = float(np.mean(chroma))
    else:
        mean_chroma = 0.0

    edge_zone = outer_edge | glyph_edge
    return {
        "outer_center_alpha_median": med(outer_center),
        "outer_edge_alpha_p90": p90(outer_edge),
        "glyph_center_alpha_median": med(glyph_center),
        "glyph_edge_alpha_p90": p90(glyph_edge),
        "max_edge_alpha": float(np.max(alpha[edge_zone])) if edge_zone.any() else 0.0,
        "opaque_pixel_fraction": float(np.mean(alpha > 0.90)),
        "high_alpha_fraction": float(np.mean(alpha > 0.50)),
        "mean_chroma": mean_chroma,
        "outer_transmission_fraction_alpha_lt_0_12": float(np.mean(alpha[om > 0.5] < 0.12)),
    }


def calibration_sheet(results: dict, cfgs: dict, debug_by_slug: dict) -> None:
    cell = 202
    icon = 154
    header = 42
    row_h = 208
    columns = (
        "official glyph mask",
        "transparent / checker",
        "white",
        "black",
        "warm wallpaper",
        "dark color",
        "complex",
    )
    sheet = Image.new("RGB", (cell * len(columns), header + row_h * len(TRIO)), (228, 229, 232))
    draw = ImageDraw.Draw(sheet)
    for c, name in enumerate(columns):
        draw.text((c * cell + 8, 14), name, fill=(25, 26, 29))

    bgs = {
        "checker": checkerboard(icon),
        "white": Image.new("RGB", (icon, icon), (248, 248, 248)),
        "black": Image.new("RGB", (icon, icon), (9, 10, 12)),
        "warm": warm_wallpaper(icon),
        "dark": dark_color_wallpaper(icon),
        "complex": complex_wallpaper(icon),
    }

    for row, slug in enumerate(TRIO):
        y0 = header + row * row_h
        im = results[slug].resize((icon, icon), Image.Resampling.LANCZOS)
        glyph_mask = debug_by_slug[slug]["glyph_mask"]
        gp = geometry_preview(glyph_mask).resize((icon, icon), Image.Resampling.LANCZOS)
        cells = [
            gp,
            composite(im, bgs["checker"]),
            composite(im, bgs["white"]),
            composite(im, bgs["black"]),
            composite(im, bgs["warm"]),
            composite(im, bgs["dark"]),
            composite(im, bgs["complex"]),
        ]
        for c, cell_im in enumerate(cells):
            x = c * cell + (cell - icon) // 2
            sheet.paste(cell_im, (x, y0 + 12))
        draw.text((8, y0 + icon + 20), cfgs[slug]["displayName"], fill=(18, 19, 21))

    sheet.save(SHEETS / "glass-in-glass-calibration.png")


def edge_sheet(results: dict, cfgs: dict, debug_by_slug: dict) -> None:
    panel = 300
    row_h = 338
    sheet = Image.new("RGB", (panel * 2, row_h * len(TRIO)), (230, 231, 233))
    draw = ImageDraw.Draw(sheet)
    warm = warm_wallpaper(r.MASTER)

    for row, slug in enumerate(TRIO):
        comp = composite(results[slug], warm)
        y0 = row * row_h

        # Outer top-left edge crop.
        outer_crop = comp.crop((32, 32, 390, 390)).resize((260, 260), Image.Resampling.LANCZOS)

        gm = debug_by_slug[slug]["glyph_mask"]
        ys, xs = np.where(gm > 0.08)
        if len(xs):
            pad = 55
            x0, x1 = max(0, xs.min() - pad), min(r.MASTER, xs.max() + pad + 1)
            yy0, yy1 = max(0, ys.min() - pad), min(r.MASTER, ys.max() + pad + 1)
            glyph_crop = comp.crop((x0, yy0, x1, yy1)).resize((260, 260), Image.Resampling.LANCZOS)
        else:
            glyph_crop = Image.new("RGB", (260, 260), (120, 120, 120))

        sheet.paste(outer_crop, (20, y0 + 42))
        sheet.paste(glyph_crop, (panel + 20, y0 + 42))
        draw.text((20, y0 + 12), f"{cfgs[slug]['displayName']} — OUTER GLASS EDGE", fill=(22, 23, 25))
        draw.text((panel + 20, y0 + 12), "INNER GLASS GLYPH", fill=(22, 23, 25))

    sheet.save(SHEETS / "glass-in-glass-edges.png")


def main() -> None:
    cfgs_all = json.loads((ROOT / "android-pack" / "launcher-mappings" / "icons.json").read_text())
    preset = json.loads((ROOT / "renderer" / "material-presets.json").read_text())["liquid_regular"]
    cfgs = {slug: cfgs_all[slug] for slug in TRIO}

    results = {}
    debug_by_slug = {}
    metrics = {}

    for slug in TRIO:
        if not any((r.OFFICIAL / f"{slug}{suffix}").exists() for suffix in (".svg", ".png", ".webp", ".jpg", ".jpeg")):
            raise FileNotFoundError(f"calibration requires official source for {slug}")
        im, _, _, _, debug = r.render_one_debug(slug, cfgs[slug], preset)
        results[slug] = im
        debug_by_slug[slug] = debug
        metrics[slug] = metrics_for(im, debug)
        im.save(OUT / f"{slug}.png")

    calibration_sheet(results, cfgs, debug_by_slug)
    edge_sheet(results, cfgs, debug_by_slug)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(metrics, indent=2, sort_keys=True))
    print("generated calibration trio:", ", ".join(TRIO))


if __name__ == "__main__":
    main()
