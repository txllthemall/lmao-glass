# Liquid Glass для Android — research baseline

This repository was bootstrapped from the complete deep-research report **«Liquid Glass для Android: техническое исследование Apple-подходов, GitHub-реализаций и адаптация под OnePlus 15»**, read in full before production work. This checked-in document is the implementation-facing digest/source map; `docs/SOURCES.md` pins the upstream material used during the audit.

## Executive conclusion

Apple Liquid Glass is not ordinary frosted glass. Its defining perceptual feature is **lensing/refraction**: content appears bent/concentrated through the material, combined with scattering/blur, transmission, adaptive tint/contrast, edge lighting, specular response, material depth/shadow and restrained environment color spill. Apple does not publish the internal Metal shader or exact optical constants, so no code in this project is presented as the Apple renderer.

For icons Apple separates flat artwork from material behavior. Icon Composer/system rendering supplies translucency, blur, shadows and highlights at runtime. Android adaptive icons expose a much smaller contract: foreground + background, plus monochrome on Android 13+. Stock launchers do not accept an icon-pack normal map, refraction coefficient, backdrop framebuffer, RuntimeShader or custom material contract.

Therefore the production architecture is:

1. **Static Liquid Glass** — primary product. Offline/baked refraction, edge response, specular, tint, internal depth and restrained dispersion in PNG/WebP/vector-composite assets.
2. **Adaptive Liquid Glass** — required Android representation using foreground/background/monochrome.
3. **Dynamic Liquid Glass** — optional reference/demo/custom-launcher path using RenderEffect + AGSL where this project controls the rendering scene.

The governing rule is **static-first, dynamic-optional**.

## Apple findings

Primary sources audited:

- WWDC25 — Meet Liquid Glass: https://developer.apple.com/videos/play/wwdc2025/219/
- WWDC25 — Say hello to the new look of app icons: https://developer.apple.com/videos/play/wwdc2025/220/
- WWDC25 — Create icons with Icon Composer: https://developer.apple.com/videos/play/wwdc2025/361/
- Icon Composer: https://developer.apple.com/icon-composer/
- HIG App icons: https://developer.apple.com/design/human-interface-guidelines/app-icons
- HIG Materials: https://developer.apple.com/design/human-interface-guidelines/materials
- SwiftUI glassEffect: https://developer.apple.com/documentation/swiftui/view/glasseffect(_:in:)
- Applying Liquid Glass to custom views: https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views

Implementation-relevant invariants:

- prioritize lensing before blur;
- highlights follow perceived surface geometry rather than being a decorative white stripe;
- material response changes with perceived size;
- keep artwork controlled/flat and material properties separate;
- avoid stacking many independent glass plates (`glass-on-glass`);
- support regular/clear and higher-contrast interpretations rather than assuming one alpha value works everywhere;
- verify at small final size and on multiple backgrounds.

Analytical model used by the research (not an Apple formula):

```text
sample background/environment at displaced coordinate
→ blur/scattering
→ tint/transmission/contrast
→ edge/rim response
→ specular
→ internal material shadow/color spill
→ foreground glyph
```

## Android constraints

Primary sources audited:

- Adaptive Icons: https://developer.android.com/develop/ui/compose/system/icon_design_adaptive
- RenderEffect: https://developer.android.com/reference/android/graphics/RenderEffect
- AGSL / RuntimeShader: https://developer.android.com/develop/ui/views/graphics/agsl
- RenderScript migration: https://developer.android.com/guide/topics/renderscript/migrate
- Hardware acceleration: https://developer.android.com/develop/ui/views/graphics/hardware-accel

Adaptive geometry baseline:

- layer canvas: **108 × 108 dp**;
- central safe area: **66 × 66 dp**;
- roughly 18 dp outer bleed on each side;
- final mask and some presentation behavior belong to the launcher/OEM;
- Android 13+ supports a monochrome layer for themed icons.

Critical limitation: the icon-pack APK cannot require OxygenOS Launcher to send the live wallpaper framebuffer through our AGSL shader. RuntimeShader applies only inside a rendering context we control. Thus real wallpaper refraction is impossible for an ordinary third-party stock-launcher icon pack and must be perceptually baked.

Do not use deprecated RenderScript as the core implementation. Runtime preview strategy:

```text
API 33+  → AGSL + RenderEffect
API 31–32 → RenderEffect where useful
older     → static/pre-rendered fallback
```

## OnePlus 15 / OxygenOS

Primary target: **OnePlus 15, OxygenOS 16, Android 16**.

Sources:

- https://www.oneplus.com/global/15
- https://www.oneplus.com/global/15/specs
- https://www.oneplus.com/us/oxygenos16

Project consequences:

- adaptive foreground/background + monochrome are mandatory outputs;
- do not assume the final OxygenOS icon mask;
- validate icon scale and clipping on the real stock launcher;
- verify third-party package mappings on the actual launcher/build;
- do not treat ColorOS and global OxygenOS behavior as an identical stable API contract;
- dynamic shader paths are allowed only inside our own preview/app/launcher rendering context.

## Open-source implementation audit

### Kyant0/AndroidLiquidGlass

Repository: https://github.com/Kyant0/AndroidLiquidGlass
Pinned commit: `65ab177e90e5c1d8c62e70cf7755841982da65f6`
License: Apache-2.0

Most useful code inspected: `backdrop/.../effects/Lens.kt` and `backdrop/.../internal/Shaders.kt`.

Its lens model uses rounded-rectangle SDF geometry, distance from the edge, a circular edge mapping, SDF gradient as a surface-direction approximation, coordinate displacement for refraction, optional depth influence and optional chromatic dispersion. This is the closest practical open-source analogue found for Apple's public description of lensing.

The optional AGSL reference in this repository is explicitly a **modified derivative** of that code and retains source/license provenance. The offline baker is an original implementation that ports the same class of edge-focused SDF/height-field idea to deterministic high-resolution prerendering rather than copying the upstream runtime architecture wholesale.

### Dimezis/BlurView

Repository: https://github.com/Dimezis/BlurView
Pinned commit: `ab56ebc7e864d673386db42e43cae81a3d330b85`
License: Apache-2.0

Used as an architectural reference for backdrop capture, downsampling and API-dependent blur backends. No source copied into production.

### chrisbanes/haze

Repository: https://github.com/chrisbanes/haze
Pinned commit: `156eddf3b0e905dac17aa48c60f139bd5f554677`
License: Apache-2.0

Used as a reference for Compose backdrop/caching/resource-lifetime decisions in a future dynamic preview. No source copied into production.

See `docs/THIRD_PARTY.md` for provenance status.

## Material reconstruction

Perceptual priority:

```text
LENSING / REFRACTION
>
EDGE + SPECULAR LIGHT
>
TRANSLUCENCY + BLUR
>
INTERNAL DEPTH / SHADOW
>
TINT / COLOR SPILL
>
CHROMATIC DISPERSION
>
NOISE
```

Recommended production chain:

```text
1024px vector master
→ 108dp logical adaptive geometry / 66dp safe area
→ glass mask
→ SDF / edge distance / height profile
→ normal/edge gradient
→ virtual environment
→ perceptual blur/scattering
→ edge-focused refraction
→ transmission/tint
→ bright rim + weaker opposite dark rim
→ broad geometry-dependent specular
→ subtle color spill
→ optional edge-only chromatic dispersion
→ internal depth/shadow
→ foreground glyph
→ bake foreground
→ adaptive FG + BG + Android 13+ monochrome
→ OxygenOS mask/scale validation
```

Normals may be derived from a height map as:

```text
N = normalize(-dh/dx, -dh/dy, z)
```

The height profile should change mainly near the outer roughly 10–20% of the glass body, so refraction reads as material thickness rather than a magnifying bubble.

## Experimental starting ranges

These are engineering calibration ranges, **not Apple specifications**:

| Effect | Starting range |
|---|---:|
| Glass body alpha | 0.14–0.28 |
| Internal blur | 4–8 dp |
| Refraction displacement | 0.6–1.8 dp |
| Refraction band | 3–8 dp |
| Bright rim | 0.6–1.5 dp, ~15–40% alpha |
| Dark inner rim | 0.4–1.2 dp, ~8–25% alpha |
| Specular width | 4–14% of diameter |
| Specular opacity | 0.18–0.48 |
| Static light/highlight angle | ~−35°…−55° |
| Internal shadow blur | 2–5 dp |
| Internal shadow alpha | 0.10–0.24 |
| Color spill | 4–15% |
| Chromatic offset | 0.15–0.7 dp, edge-only |
| Frost/noise | 0.5–2% |
| Glyph opacity | 0.88–1.00 |

All icons must share one light vector, material/refraction family, roughness family, rim behavior, shadow softness and virtual environment.

## Artwork/material separation

Source artwork must not contain generic baked glass effects. Keep:

```text
glyph/vector artwork
+
glass mask / height / material parameters / virtual light environment
→ renderer
→ outputs
```

This allows material tuning to regenerate hundreds of icons consistently rather than hand-editing PNGs.

## Output strategy

Preferred hybrid:

```text
BG     → vector/color
Glass  → prerendered high-quality PNG/WebP
Glyph  → vector where useful, baked where interaction is required
Mono   → vector/clean alpha geometry
```

Do not force refraction, normal-map lighting, complex blur or dispersion into VectorDrawable purely to remain vector.

## QA suite

The initial family intentionally contains distinct geometric classes:

1. Telegram
2. Discord
3. GitHub
4. Google Play
5. Pinterest
6. Kaspi.kz
7. 2GIS
8. YouTube ReVanced
9. GameHub

Do not scale to hundreds of icons until these read as one material family.

Visual QA must include:

- 1024 master, 512 and launcher-size previews;
- white, black, neutral gray, saturated color and complex wallpaper backgrounds;
- optical centering and perceived scale, not mathematical centering only;
- edge preservation after downsampling;
- absence of alpha halos/clipping;
- one consistent light/specular direction;
- recognizable brand geometry;
- correct monochrome behavior.

Reject the renderer if the result can be described as:

```text
rounded rectangle
+ constant alpha
+ Gaussian blur
+ white stroke
+ decorative linear highlight
+ drop shadow
```

That is generic glassmorphism, not the target material.

## Release caveats

- Apple does not publish exact Liquid Glass shader coefficients; every numeric optical parameter here is a reconstruction/calibration value.
- 2GIS, Kaspi.kz and GameHub QA masters currently need verified vendor source artwork before public distribution.
- ReVanced branding has permission restrictions separate from its code licensing; the QA master is deliberately not the exact official upstream asset.
- Real OnePlus 15/OxygenOS 16 device tests remain mandatory for mask, scaling, transparent-background and package-mapping behavior.
- Dynamic AGSL performance must be measured separately; it is not required for ordinary static icon-pack runtime.

## Definition of success

The pack is not done because the build succeeds. It is done only when lensing reads at launcher size, the edge suggests real thickness, specular follows the inferred surface, transparency does not become milky plastic, glyphs remain identifiable and optically aligned, the nine-icon set reads as one material family, and OxygenOS does not clip or distort the assets.
