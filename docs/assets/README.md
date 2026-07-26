# Brand and media assets

| File | Use |
| --- | --- |
| `logo.svg` | The hexagon mark on a dark chip. Reads on light and dark. |
| `favicon.svg` | The mark for browser tabs and docs sites. |
| `og-image.svg` | Social-preview card (1200x630) source. |
| `demo.tape` | [VHS](https://github.com/charmbracelet/vhs) script that renders `demo.gif`. |

Palette: accent `#37E5C4`, deep accent `#0FA890`, amber `#E29A34`, background
`#0A0F15`, ink `#DCE6EF`.

## Regenerating the demo GIF

```sh
vhs docs/assets/demo.tape   # writes docs/assets/demo.gif
```

See the comments in `demo.tape` for recording against the bundled fake Core, so
no proprietary runtime is needed.

## Social preview (owner step)

GitHub's social preview needs a raster image. Export `og-image.svg` to a 1200x630
PNG and upload it under Settings, General, Social preview:

```sh
rsvg-convert -w 1200 -h 630 docs/assets/og-image.svg -o og-image.png
```
