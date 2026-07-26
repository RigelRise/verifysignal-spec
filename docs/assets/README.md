# Brand & media assets

| File | Use |
| --- | --- |
| `logo.svg` | The mark (signal → check), teal on transparent. Works on light and dark. |
| `wordmark.svg` | Mark + "VerifySignal" lockup for light backgrounds. |
| `favicon.svg` | 32×32 mark for browser tabs / docs sites. |
| `og-image.svg` | Social-preview card (1200×630) source. |
| `demo.tape` | [VHS](https://github.com/charmbracelet/vhs) script that renders `demo.gif`. |

## Regenerating the demo GIF

```sh
# one-time: install VHS (https://github.com/charmbracelet/vhs)
vhs docs/assets/demo.tape   # writes docs/assets/demo.gif
```

See the comments in `demo.tape` for recording against the bundled fake Core so no
proprietary runtime is needed for a demo cut.

## Social preview (owner step)

GitHub's social preview needs a raster image. Export `og-image.svg` to a
1200×630 PNG and upload it under **Settings → General → Social preview**:

```sh
# any SVG rasterizer works, e.g.
rsvg-convert -w 1200 -h 630 docs/assets/og-image.svg -o og-image.png
# or: npx svgexport docs/assets/og-image.svg og-image.png 1200:630
```

Brand palette: **signal teal** `#0C9A8C` (light) / `#22C1AE` (dark), ink `#0E1719`,
paper `#F4F7F7`, amber accent `#E0A836`.
