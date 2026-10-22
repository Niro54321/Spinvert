# Spinvert

**Drag a file. Hold a key. Drop it on a format.**
Fast, offline file conversion for Windows, right where your files already are.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows 10 | 11](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![Version: 0.1.0](https://img.shields.io/badge/version-0.1.0-7C5CFF)
![Offline: 100%](https://img.shields.io/badge/uploads-none-success)

---

## Why

To turn a HEIC photo into a JPG, a WAV into an MP3, or a 200 MB video into
something you can email, most people end up on a website that uploads the
file to a stranger's server. Others open a heavy app just to click "Export".

Spinvert removes those steps. Start dragging a file in File Explorer, press
**Shift**, and a wheel of formats opens under your cursor. Drop the file on
the format you want, and the converted copy appears next to the original.
Nothing leaves your PC.

## How it works

| While you drag, press... | Wheel | What you get |
| --- | --- | --- |
| **Shift** | Convert | Every format that makes sense for that file: PNG, WebP, MP3, MP4, PDF... |
| **Ctrl** | Tools | Compress, combine images into a PDF, merge, split and reorder PDFs, remove metadata, normalize volume, remove sound, ZIP |

- The wheel only shows options that fit the file you are dragging.
- It stays open after you let go of the key, until you drop or press **Esc**.
- Press the other key while the wheel is open to switch wheels.
- Drag many files at once and they are converted as a batch, with a progress window.
- The original is never changed. The result is always a **new copy** beside it.
- Spinvert lives in the system tray. Both keys can be changed in Settings.

Other ways in, for when dragging isn't handy:

- **Drop window**: click the tray icon, drop files on the box, pick from the wheel.
- **Send to**: turn it on in Settings, then right-click files → *Send to* → *Spinvert*.

## Conversions

| Category | Convert to | Tools |
| --- | --- | --- |
| Images (JPG, PNG, WebP, TIFF, BMP, GIF, HEIC, AVIF) | JPG, PNG, WebP, TIFF, BMP, GIF, PDF | Compress, combine into one PDF, remove metadata |
| Audio (MP3, M4A, WAV, FLAC, OGG, Opus, AAC, WMA, AIFF) | MP3, M4A, WAV, FLAC, OGG, Opus | Normalize volume |
| Video (MP4, MOV, MKV, WebM, AVI, WMV and more) | MP4, MOV, MKV, WebM, AVI, GIF, MP3 | Compress, remove sound |
| PDF | JPG, PNG (every page at 300 DPI), TXT, PPTX | Merge, split pages, reorder or remove pages, compress |
| Documents (DOCX, Markdown, HTML, EPUB, ODT, RTF, TXT) | DOCX, PDF, Markdown, HTML, EPUB, TXT | |
| Slides (PPTX, PPT) | PDF, PNG, JPG (with PowerPoint), TXT, Markdown | |
| Spreadsheets (XLSX, XLS, CSV, TSV) | XLSX, CSV, TSV, PDF (with Excel) | |
| Subtitles (SRT, VTT) | SRT, VTT, TXT | |
| Archives (ZIP, TAR, TAR.GZ, GZ) and folders | Extract, ZIP, TAR, TAR.GZ | ZIP everything you dragged |

Video to MP4, MOV, MKV or WebM is a quick re-wrap with no quality loss when
the codecs already fit, and a re-encode only when they don't.

## Install and run

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/).
2. Install **FFmpeg** for audio and video:
   ```bash
   winget install Gyan.FFmpeg
   ```
3. Download this repository (green **Code** button → *Download ZIP*, or `git clone`).
4. Double-click **`Spinvert.bat`**. The first run sets everything up, which takes a
   minute or two. After that it starts at once.

Optional: with **Microsoft Office** installed, Spinvert uses Word, PowerPoint
and Excel for the best Office-to-PDF output, and for slides to images. Without
Word, documents still convert to PDF with Spinvert's own writer.

## Privacy

- No uploads. Every conversion runs on your own PC.
- No account, no sign-in, no telemetry, no network calls.
- To spot the drag, Spinvert checks the state of the mouse button and of
  Shift, Ctrl, Alt and Esc a few dozen times a second. It does not record
  keystrokes and installs no keyboard hooks.
- For the glass look, Spinvert keeps a snapshot of the screen behind the wheel
  (taken when you press the mouse in File Explorer) and behind its own window.
  It stays in memory, is replaced at the next press, and is never saved or sent.

## Roadmap

- [x] **Research**: features, flows and a feature matrix ([`replica/`](replica/))
- [x] **v0.1, Convert and Tools**: both wheels, every format in the table above, batch jobs, progress window, tray, settings, Send to, start with Windows
- [ ] **v0.2, More tools**: compress to an exact size, trim audio and video, crop images, strip metadata from audio, video and PDF
- [ ] **v0.3, Windows touches**: Actions wheel (copy path, move, open in Terminal, share), global hotkey, a real Explorer right-click menu
- [ ] **v1.0**: a one-click installer with FFmpeg included, and simple editors

Progress against the plan is tracked in [`replica/features.csv`](replica/features.csv)
(all 12 must-haves are done).

## Development

```bash
.venv\Scripts\python.exe tests\smoke_test.py
```

The smoke test generates sample files of every type, runs every conversion and
tool on them, and checks each output opens. Add `--no-office` to test the
paths used on PCs without Microsoft Office.

| Folder | What is in it |
| --- | --- |
| `spinvert/engines/` | One module per file family: images, media, pdfs, documents, slides, sheets, subtitles, archives, office |
| `spinvert/catalog.py` | Every operation, and which ones fit a selection of files |
| `spinvert/watcher.py` | Spots a file drag plus a key press |
| `spinvert/wheel.py` | The radial wheel and its drop handling |
| `replica/` | The product research: recon map and feature matrix |

Built on [FFmpeg](https://ffmpeg.org/), [Pillow](https://python-pillow.org/),
[pillow-heif](https://github.com/bigcat88/pillow_heif), [pypdf](https://github.com/py-pdf/pypdf),
[PDFium](https://pdfium.googlesource.com/pdfium/) via pypdfium2, [Pandoc](https://pandoc.org/),
[openpyxl](https://openpyxl.readthedocs.io/), [python-pptx](https://python-pptx.readthedocs.io/)
and [Qt for Python](https://doc.qt.io/qtforpython/). FFmpeg and Pandoc run as
separate programs under their own licences.

## Contributing

- **Ideas and requests**: open an [issue](../../issues) and say which formats or tools you need most.
- **Bugs**: include the file type, what you pressed, and the message in the progress window.
- **Code**: run the smoke test before opening a pull request.

## Inspiration and disclaimer

The drag-and-key workflow is inspired by
[Tangerine for Mac](https://tangerineformac.com/) by Leap Studio, which is
only available on macOS. Spinvert is an independent project for Windows. It
is not affiliated with or endorsed by Leap Studio, and it uses none of
Tangerine's code, assets, artwork or text. "Spinvert" is a working name.

## License

[MIT](LICENSE) © 2026 Niro54321
