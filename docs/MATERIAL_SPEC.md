# Liquid Glass material specification

Apple does not publish the internal Liquid Glass Metal shader or optical constants. The project therefore reproduces source-backed visual invariants rather than claiming an Apple formula.

## Visual priority
1. Lensing / edge-focused refraction
2. Edge and specular response
3. Translucency + scattering/blur
4. Internal depth / shadow
5. Tint / environment color spill
6. Restrained chromatic dispersion
7. Micro-noise / dither

## Pipeline
`shape/SDF -> edge distance -> height -> normals -> virtual backdrop blur -> refraction -> transmission/tint -> light/dark rim -> broad specular -> color spill -> restrained dispersion -> glyph -> bake`

The edge profile changes mainly in the outer 10–20% of the glass body so lensing reads as thickness rather than a magnifying bubble.

## Experimental ranges
These are not Apple specifications: glass alpha 0.14–0.28; blur 4–8 dp; refraction 0.6–1.8 dp; refraction band 3–8 dp; bright rim 0.6–1.5 dp at 15–40%; dark inner rim 0.4–1.2 dp at 8–25%; specular 0.18–0.48; chromatic offset 0.15–0.7 dp; noise 0.5–2%; glyph alpha 0.88–1.00.

All icons share one light vector, roughness family, rim family and virtual environment. Reject any result that reduces to `roundedRect + alpha + Gaussian blur + white stroke + gradient + drop shadow`.
