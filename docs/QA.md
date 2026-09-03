# QA specification

Review every QA icon at 1024 px, 512 px and launcher scale on white, black, neutral gray, saturated color and complex wallpaper. Reject hard white rims, milky glass, full-perimeter RGB fringe, pasted-on glyphs, visual scale mismatch or alpha halos.

`validate.py` checks all nine generated icons, dimensions, alpha, package metadata, adaptive XML and glyph-derived monochrome output.

Before release test on a real OnePlus 15 / OxygenOS 16 stock launcher: masking, icon size, themed/monochrome behavior, transparent background behavior and third-party pack mapping.
