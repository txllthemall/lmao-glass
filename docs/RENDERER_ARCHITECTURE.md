# Renderer architecture

## Static-first
The stock Android launcher receives drawables, not a programmable material. Production output is prerendered foreground + standard adaptive icon layers.

## Offline baker
`renderer/offline_renderer/render.py` renders at 1024 px, derives distance/height/normal data procedurally, applies an edge-band circular refraction profile, then Lanczos-downsamples.

## Dynamic reference
`renderer/agsl-preview/liquid_glass_reference.agsl` is a clearly marked Apache-2.0 modified derivative of Kyant0/AndroidLiquidGlass at the pinned commit in `SOURCES.md`. It is for an app/preview/custom-launcher rendering context only.

## Android output
- foreground: baked optical material + glyph
- background: transparent neutral prototype drawable
- monochrome: glyph-derived white alpha bitmap

Transparent adaptive background behavior must be validated on OxygenOS 16 and replaced by a controlled fallback if required.
