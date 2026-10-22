# Spinvert

**Drag a file. Hold a key. Drop it on a format.**
Fast, offline file conversion for Windows, right where your files already are.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows 10 | 11](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![Status: planning](https://img.shields.io/badge/status-planning-orange)
![Offline: 100%](https://img.shields.io/badge/uploads-none-success)

---

> **Project status: planning.** The product research is done (see
> [`replica/recon.md`](replica/recon.md)). The architecture is next, then the
> first build. Star or watch the repo to follow along.

## Why

To turn a HEIC photo into a JPG, a WAV into an MP3, or a 200 MB video into
something you can email, most people end up on a website that uploads the
file to a stranger's server. Others open a heavy app just to click "Export".

Spinvert removes those steps. Start dragging a file in File Explorer, press
**Shift**, and a wheel of formats opens under your cursor. Drop the file on
the format you want, and the converted copy appears next to the original.
Nothing leaves your PC.

## How it works

| While you drag, hold... | Wheel | What you get |
| --- | --- | --- |
| **Shift** | Convert | Every format that makes sense for that file: PNG, WebP, MP3, MP4, PDF... |
| **Ctrl** | Tools | Compress (by quality, a percentage or an exact size), trim, crop, merge, split, strip metadata |
| **Alt** | Actions | Copy, Move, Copy path, Open in Terminal, Share |

- The wheel only shows options that fit the file you are dragging.
- It stays open after you let go of the key, until you drop or press **Esc**.
- Drag many files at once and they are converted as a batch, with a progress window.
- The original is never changed. The result is always a **new copy**.
- Every key can be changed in Settings. Spinvert lives in the system tray.

## Planned formats

| Category | Formats |
| --- | --- |
| Images | JPG, PNG, WebP, TIFF, BMP, GIF, HEIC and AVIF input, image to PDF |
| Audio | MP3, M4A, WAV, FLAC, OGG, Opus |
| Video | MP4, MOV, MKV, WebM, AVI, video to GIF, video to MP3 |
| PDF | PDF to JPG/PNG, merge, split, reorder, compress |
| Later | DOCX, EPUB, Markdown, PPTX, XLSX, CSV, SRT/VTT subtitles, ZIP/TAR/GZIP archives |

## Roadmap

- [x] **Research**: features, flows and a feature matrix ([`replica/`](replica/))
- [ ] **Architecture**: stack, conversion engines, licence check for every bundled engine
- [ ] **v0.1, Convert**: Shift wheel for images, audio and video, batch jobs, tray icon, settings
- [ ] **v0.2, Tools**: compression (including exact target size), trim, crop, metadata removal, PDF merge and split
- [ ] **v0.3, Windows touches**: Actions wheel, Explorer right-click menu, global hotkey, start with Windows
- [ ] **v1.0**: documents, slides, spreadsheets, subtitles, archives, and simple editors

The full list, with priorities, is in [`replica/features.csv`](replica/features.csv).

## Privacy promise

- No uploads. Every conversion runs on your own PC.
- No account, no sign-in, no telemetry.
- Free and open source, with no "20 free files" limit.

## Project documents

| File | What is in it |
| --- | --- |
| [`replica/recon.md`](replica/recon.md) | The research map: screens, user flows, components, data model, the hard parts, and the size estimate |
| [`replica/features.csv`](replica/features.csv) | Feature matrix: 52 features ranked must / should / could, with progress tracking |

## Contributing

The project is at an early stage, and this is the best time to shape it.

- **Ideas and requests**: open an [issue](../../issues) and say which formats or tools you need most.
- **Windows know-how**: help is welcome with drag-and-drop hooks, shell integration and installers.
- **Code**: after the architecture lands, issues tagged `good first issue` will be the place to start.

## Inspiration and disclaimer

The drag-and-key workflow is inspired by
[Tangerine for Mac](https://tangerineformac.com/) by Leap Studio, which is
only available on macOS. Spinvert is an independent project for Windows. It
is not affiliated with or endorsed by Leap Studio, and it uses none of
Tangerine's code, assets, artwork or text. "Spinvert" is a working name.

## License

[MIT](LICENSE) © 2026 Niro54321
