# Chisel brand artwork

The Chisel logo: an open book, half rough stone and half a page of text, with a chisel working at the join.
The artwork was supplied by the project author.

| File | What it is | Use it for |
|---|---|---|
| `chisel-icon.svg` | The logo on a rounded square with a pale background, as a vector. | App icons, the in-app logo, the favicon, social previews. It is the same artwork as `gui/src/assets/logo.svg`. |
| `chisel-icon-1024.png` | The same icon rendered at 1024 x 1024 pixels. | The README, documents and anywhere a bitmap is needed. |
| `chisel-mark.svg` | The logo alone, with no background square, as a vector. | Placing the logo on a background of your own, for example a slide, a page header or a dark theme. |
| `chisel-mark-1024.png` | The same mark rendered at 1024 x 1024 pixels. | Bitmap uses of the mark. |

The icon and the mark show the same drawing. Use the icon where the logo stands alone as an app icon, and the
mark where it sits next to text or on a surface that already has its own colour.

## Where the artwork is used in the code

- `gui/src/assets/logo.svg` is a copy of `chisel-icon.svg`, shown by the `Logo` component in the desktop UI
  (`gui/public/logo.svg` and `favicon.png` are copies for the page).
- `gui/src-tauri/icons/` holds the sized PNGs, `icon.ico` and `icon.icns` that the installers and bundles use.
  `gui/scripts/make-icons.sh` regenerates them from `gui/src/assets/logo.svg`.
- `src/chisel/gui/icon.ico` (Windows) and `icon.png` (macOS and Linux) are the desktop window's icon.

The details and the reason for the two window icons are in [../dev/packaging.md](../dev/packaging.md#icons).
