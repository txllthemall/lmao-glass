# lmao-glass

Experimental Android Liquid Glass icon-system for **OnePlus 15 / OxygenOS 16**, built from a static-first renderer with an optional AGSL reference implementation.

## Status

`liquid-glass-v1` is an engineering prototype. The renderer and nine-icon QA suite are intended to calibrate the material before any mass icon generation.

## Principles

- lensing/refraction before blur
- artwork and material are separate
- static baked assets are the product; dynamic shader is a reference/demo
- one global lighting/material environment for the whole family
- adaptive icon geometry: 108 dp canvas, 66 dp safe zone
- explicit provenance for every third-party source

## Build

```bash
python -m pip install -r requirements.txt
python renderer/offline_renderer/render.py --all
python renderer/offline_renderer/validate.py
```

Generated previews land in `generated/`.

## Warning

The current 2GIS, Kaspi.kz and GameHub vector masters are **visual reconstructions of current app-icon references**, not vendor-provided source vectors. They are kept in the QA suite so geometry/material can be tested, but must be replaced with verified official assets before a public release. ReVanced branding has separate upstream permission rules; see `docs/THIRD_PARTY.md`.
