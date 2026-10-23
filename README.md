# Spinvert

**Drag a file. Hold a key. Drop it on a format.**
Fast, offline file conversion for Windows, right where your files already are.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows 10 | 11](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
[![Version: 0.2.1](https://img.shields.io/badge/version-0.2.1-7C5CFF)](https://github.com/Niro54321/Spinvert/releases/latest)
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
| **Ctrl** | Tools | Edit, crop, resize, annotate and redact photos; trim, crop, speed up and split videos; trim and bleep audio; organize PDFs… ([all tools](#tools)) |

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
| Images (JPG, PNG, WebP, HEIC, TIFF, AVIF, BMP, GIF, SVG) | JPG, PNG, WebP, HEIC, TIFF, AVIF, BMP, GIF, PDF | see [Tools](#tools) |
| Audio (MP3, M4A, WAV, FLAC, OGG, Opus, AIFF, WMA, AAC) | MP3, M4A, WAV, FLAC, OGG, Opus, AIFF, WMA | see [Tools](#tools) |
| Video (MP4, MOV, MKV, WebM, AVI, WMV and more) | MP4, MOV, MKV, WebM, AVI, WMV, GIF, MP3 | see [Tools](#tools) |
| PDF | DOCX, PPTX, XLSX, JPG, PNG (every page at 300 DPI), EPUB, TXT, Markdown | see [Tools](#tools) |
| Documents (DOCX, Markdown, HTML, EPUB, ODT, RTF, TXT, and RTFD and text clippings from a Mac) | DOCX, PDF, Markdown, HTML, EPUB, TXT | |
| Pages (read only) | PDF, DOCX, Markdown, EPUB, TXT, JPG, PNG | |
| Slides (PPTX, PPT) | PDF, PNG, JPG (with PowerPoint), TXT, Markdown | |
| Spreadsheets (XLSX, XLS, ODS, CSV, TSV) | XLSX, ODS, CSV, TSV, PDF (with Excel) | |
| Subtitles (SRT, VTT) | SRT, VTT, TXT | |
| Archives (ZIP, TAR, GZIP, RAR) and folders | Extract, ZIP, TAR, GZIP | ZIP everything you dragged |

- Video to MP4, MOV, MKV or WebM is a quick re-wrap with no quality loss when
  the codecs already fit, and a re-encode only when they don't.
- PDF to DOCX, EPUB and Markdown rebuilds the document: paragraphs, headings,
  tables and pictures. A scanned page comes through as a picture. Layouts with
  several columns or forms come out simpler than the original.
- PDF to XLSX turns the PDF's tables into sheets, one per page.
- Pages files are read through the full PDF copy that Pages keeps inside them.
  Writing `.pages` isn't possible outside Apple's own apps.
- RAR files open with the `tar` tool that Windows 10 and 11 include.

## Tools

Press **Ctrl** while dragging (or click the hub of the wheel). Tools that need
settings open a glass editor with a live preview; the result is always a new copy.

| For | Tools |
| --- | --- |
| **Any file** | **Compress**: by quality, to a target size (MB), or by a percentage. **Metadata**: see every field (searchable), change title, artist, date…, remove everything or just the location. **ZIP** |
| **Photos** | **Edit**: exposure, contrast, highlights, shadows, whites, blacks, temperature, tint, vibrance, saturation, clarity, dehaze, sharpness, noise reduction, grain, vignette, plus presets (Vivid, Punch, Warm, Cool, Matte, Fade, Vintage, Dramatic, B&W). **Crop**: free or 1:1, 4:5, 9:16, 16:9…, rotate, flip, exact output pixels. **Resize**: 25% to 400% or an exact size, with sharpening for upscales. **Add BG**: gradients (or design your own), colours (or pick any), a blurred copy or your own image, with padding, rounded corners, shadow and ratio; several pictures go side by side, stacked or in a grid as one image. **Annotate**: a layer editor; arrows, boxes, circles, lines, pen, highlighter, text typed right on the picture (any font, size, background, shadow, Arabic included), numbered labels, magnifier and pictures; select, move, resize, right-click menu, layers you drag to reorder, undo. **Redact**: blur, pixelate or cover with a strength; finds faces and text for you. **Text**: reads the words in a picture. Several photos: **Collage** (grid, row, column, featured; drag each picture to choose what shows, scroll to zoom) and **To PDF** |
| **Video** | Every video editor plays with sound: Play/Pause, 10 s back and forward, preview at 0.5× to 4×; Space and the arrow keys work too. **Trim & edit** (exact times, frame steps, save at 0.25× to 4×, text and picture layers that show for their own time range, extra sound tracks with volume, mute the original), **Crop** (Reels / TikTok 9:16, square, 4:5, 16:9 or free; crop to fill, or fit on a blurred copy of the video, a colour, a gradient or an image), **Speed**, **Frames** (full-size PNGs), **Split**, **Redact** (blur, pixelate or cover with a strength, each box with its own time range, previewed live), **Mute**. Several clips: **Join** into one MP4 |
| **Audio** | **Trim** (waveform, playback with sound, exact times, fade in and out, remove silence at the ends, save at another speed), **Normalize** (streaming, podcast or broadcast loudness, two-pass, shows before and after), **Visualize** (waveform or bars video in landscape, portrait or square, on a colour or your image), **Channels** (mono, stereo, left, right, swap, volume per side, listen to each), **Bleep** (mark parts on the waveform, beep or silence, compare), **Speed**, **Split**. Several files: **Join**, with a gap of silence between them if you like |
| **PDF** | **Organize** pages (reorder, rotate, duplicate, remove), **Split** (every page, every N pages, or ranges like 1-3, 4-), **Password** (lock with AES-256 or unlock), **Text** (reads scanned pages), **Compress**. Several PDFs: **Merge** in your order |

### Screenshots

Press **Ctrl+Alt+S** anywhere (or *Take a screenshot* in the tray menu, or the
**Screenshot** button). To use other keys, open Settings, click the shortcut and press
the keys you want (F9, Shift+F1, Print Screen...); Spinvert tells you at once if
another app on your PC already has them. Drag to capture an area, or just click to take the whole
screen; Esc cancels. The picture opens in the same layer editor as Annotate,
starting on **Blur**: blur or pixelate anything private, type text in Arabic or
English with any font installed on your PC, add arrows, boxes, numbers. Then
**Copy** (Ctrl+C) puts it on the clipboard without saving a file, or **Save…**
(Ctrl+S) writes a PNG or JPG to *Pictures\Spinvert Screenshots*.

**Share link** (Ctrl+D) uploads the picture and copies a link to it, ready to
paste in a chat. Links are random and can't be guessed, pages are hidden from
search engines, and a picture is deleted after a year. Every picture you share
gets its own delete link, listed in *Settings → Shared links*. Please share only
what you have the right to share; illegal content is removed and reported.

Every editor window can be resized from its edges, filled to the screen with the
▢ button (or a double-click on its title), and drag the line between the picture
and the settings to give either more room. Controls move onto a second line when
the window is narrow, and the window never gets small enough to cut a button off.

### Beyond Tangerine

Ideas added on top of the original, from what users of file converters ask for:

- **Text recognition (OCR)** for pictures and scanned PDFs, offline, using Windows' own engine (Arabic and English included). The text is saved as a .txt and copied to the clipboard.
- **Automatic face and text finding** in Redact.
- **Social video presets**: Reels / TikTok / Shorts 9:16, square, 4:5 and 16:9, at exact sizes like 1080 × 1920.
- **Upscaling** pictures to 2×, 3× or 4×, or any exact size.
- **Fades and silence removal** when trimming audio.
- **PDF password** lock and unlock, and **split by page ranges**.
- **Several pictures to PDF**: Spinvert asks whether you want one PDF for all of them or one each, and lets you set the page order.
- **Target-size compression** for photos, video and audio, not only PDFs.
- **Join and split audio** as well as video.
- No 20-file limit, no account, and Windows touches: *Send to* menu, start with Windows.

## Install

**[Download Spinvert-Setup-0.2.1.exe](https://github.com/Niro54321/Spinvert/releases/latest)**
from the latest release and run it. Nothing else to install: Python and every
library are inside. It installs for your Windows account only, so it needs no
admin rights, and it can download **FFmpeg** (for audio and video) for you.

The installer isn't code-signed yet, so Windows SmartScreen may say *"Windows
protected your PC"*. Click **More info → Run anyway**. Uninstall it from
*Settings → Apps* like any other app.

### Run from source

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

- No uploads. Every conversion runs on your own PC. The one exception is a
  screenshot you choose to share with **Share link**: that picture, and only
  that picture, goes to Spinvert's share server (a Cloudflare Worker, code in
  [`server/`](server/)), which keeps no account, name or log of who uploaded it.
- No account, no sign-in, no telemetry. Spinvert connects to the internet only
  when you press Share link.
- To spot the drag, Spinvert checks the state of the mouse button and of
  Shift, Ctrl, Alt and Esc a few dozen times a second. It does not record
  keystrokes and installs no keyboard hooks.
- For the glass look, Spinvert keeps a snapshot of the screen behind the wheel
  (taken when you press the mouse in File Explorer) and behind its own window.
  It stays in memory, is replaced at the next press, and is never saved or sent.
- Screenshots are taken only when you ask (your shortcut, the tray menu or the
  button), and saved only when you press Save.

## Roadmap

- [x] **v0.1, Convert and Tools**: both wheels, every format in the table above, batch jobs, progress window, tray, settings, Send to, start with Windows
- [x] **v0.2, More tools**: editors for photos, video, audio and PDF, compress to an exact size, metadata, screenshots, and a one-click installer
- [ ] **v0.3, Windows touches**: Actions wheel (copy path, move, open in Terminal, share), a real Explorer right-click menu
- [ ] **v1.0**: a signed installer and automatic updates

## Development

```bash
.venv\Scripts\python.exe tests\smoke_test.py
```

The smoke test generates sample files of every type, runs every conversion and
tool on them, and checks each output opens. Add `--no-office` to test the
paths used on PCs without Microsoft Office.

To build the installer (needs `pip install pyinstaller` in the venv and
[Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```bash
.venv\Scripts\python.exe packaging\build.py
```

It packages the app with PyInstaller, runs the smoke test and a video playback
check inside the packaged app, then writes `dist\Spinvert-Setup-<version>.exe`.

| Folder | What is in it |
| --- | --- |
| `spinvert/engines/` | One module per file family: images, media, pdfs, documents, slides, sheets, subtitles, archives, office |
| `spinvert/catalog.py` | Every operation, and which ones fit a selection of files |
| `spinvert/watcher.py` | Spots a file drag plus a key press |
| `spinvert/wheel.py` | The radial wheel and its drop handling |
| `packaging/` | The installer: PyInstaller recipe, Inno Setup script, build and self-test |
| `server/` | The share server for screenshot links: a Cloudflare Worker with R2 storage |

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
