"""Text and face detection with Windows' own engines (Windows.Media.Ocr and
Windows.Media.FaceAnalysis): offline, nothing to install, and OCR reads every
language pack installed in Windows (Arabic and English on many PCs).

Windows PowerShell can call these WinRT APIs directly, so a small script does
the work and prints JSON.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from spinvert.util import CREATE_NO_WINDOW, ConversionError, app_data_dir

SCRIPT = r"""
param([string]$Path, [string]$Mode = "text")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.FaceAnalysis.FaceDetector, Windows.Media, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$ImgW = [double]$bitmap.PixelWidth; $ImgH = [double]$bitmap.PixelHeight  # PowerShell names ignore case
if ($Mode -eq "faces") {
    $gray = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert($bitmap, [Windows.Graphics.Imaging.BitmapPixelFormat]::Gray8)
    $detector = Await ([Windows.Media.FaceAnalysis.FaceDetector]::CreateAsync()) ([Windows.Media.FaceAnalysis.FaceDetector])
    $faces = Await ($detector.DetectFacesAsync($gray)) ([System.Collections.Generic.IList[Windows.Media.FaceAnalysis.DetectedFace]])
    $boxes = @(); foreach ($f in $faces) { $b = $f.FaceBox
        $boxes += ,@(($b.X / $ImgW), ($b.Y / $ImgH), (($b.X + $b.Width) / $ImgW), (($b.Y + $b.Height) / $ImgH)) }
    ConvertTo-Json -InputObject @{ faces = $boxes } -Depth 5 -Compress
    exit
}
$best = $null; $bestCount = -1
foreach ($lang in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
    if ($engine -eq $null) { continue }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $count = ($result.Text -replace '\s', '').Length
    if ($count -gt $bestCount) { $best = $result; $bestCount = $count; $bestLang = $lang.LanguageTag }
}
$lines = @()
foreach ($line in $best.Lines) {
    $words = @(); foreach ($word in $line.Words) { $r = $word.BoundingRect
        $words += ,@{ text = $word.Text; box = @(($r.X / $ImgW), ($r.Y / $ImgH), (($r.X + $r.Width) / $ImgW), (($r.Y + $r.Height) / $ImgH)) } }
    $lines += ,@{ text = $line.Text; words = $words }
}
ConvertTo-Json -InputObject @{ language = $bestLang; lines = $lines } -Depth 8 -Compress
"""

MAX_SIDE = 4000


def _script() -> Path:
    path = app_data_dir() / "winrt-vision-1.ps1"
    if not path.exists() or path.read_text(encoding="utf-8-sig") != SCRIPT:
        path.write_text(SCRIPT, encoding="utf-8-sig")
    return path


def _run(image: Image.Image, mode: str, ctx=None) -> dict:
    with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
        png = Path(tmp) / "page.png"
        im = image.convert("RGB")
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        im.save(png)
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(_script()), "-Path", str(png), "-Mode", mode]
        if ctx is not None:
            text = ctx.run(cmd, capture=True)
        else:
            done = subprocess.run(cmd, capture_output=True, timeout=120, creationflags=CREATE_NO_WINDOW)
            if done.returncode != 0:
                raise ConversionError("Windows couldn't read this picture.")
            text = done.stdout.decode("utf-8", "replace")
    try:
        return json.loads(text.strip() or "{}")
    except ValueError as e:
        raise ConversionError("Windows couldn't read this picture.") from e


def read_text(image: Image.Image, ctx=None) -> dict:
    """{language, lines: [{text, words: [{text, box}]}]}; boxes are fractions."""
    return _run(image, "text", ctx)


def find_faces(image: Image.Image) -> list:
    return _run(image, "faces").get("faces") or []


def text_boxes(image: Image.Image) -> list:
    """One box per word, for 'Detect text' in Redact."""
    return [w["box"] for line in read_text(image).get("lines", []) for w in line.get("words", [])]


def extract_text(ctx):
    """Picture or scanned PDF to a .txt file, and onto the clipboard."""
    from spinvert.catalog import category

    src = ctx.inputs[0]
    pages = []
    if category(src) == "pdf":
        from spinvert.engines.pdfs import _open_pdfium, _render

        pdf = _open_pdfium(src)
        try:
            for i in range(len(pdf)):
                ctx.check()
                result = read_text(_render(pdf[i], 200), ctx)
                pages.append("\n".join(line["text"] for line in result.get("lines", [])))
                ctx.progress((i + 1) / len(pdf))
        finally:
            pdf.close()
    else:
        from spinvert.engines.images import _open, _upright

        result = read_text(_upright(_open(src)), ctx)
        pages.append("\n".join(line["text"] for line in result.get("lines", [])))
    text = "\n\n".join(p for p in pages if p.strip()).strip()
    if not text:
        raise ConversionError("No text found in this picture.")
    out = ctx.output(f"{src.stem} (text)", "txt")
    out.write_text(text + "\n", encoding="utf-8")
    try:
        from spinvert.mainthread import run_in_main

        def copy():
            from PySide6.QtGui import QGuiApplication

            QGuiApplication.clipboard().setText(text)

        run_in_main(copy)
    except Exception:
        pass  # the .txt file is the result; the clipboard is a bonus
    return [out]
