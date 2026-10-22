"""Audio and video with FFmpeg: conversions, the tools, and quick previews
(single frames, thumbnail strips, waveforms) for the editors."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from spinvert.util import (CREATE_NO_WINDOW, ConversionError, ext_of, find_ffmpeg, find_ffprobe,
                           natural_key)

AUDIO_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "aiff": ["-c:a", "pcm_s16be"],
    "wma": ["-c:a", "wmav2", "-b:a", "192k"],
}
AUDIO_ALIAS = {"aac": "m4a", "aif": "aiff", "oga": "ogg"}
LOSSY_KBPS = {"mp3": "libmp3lame", "m4a": "aac", "ogg": "libvorbis", "opus": "libopus", "wma": "wmav2"}

# Containers that can take these codecs as they are, without re-encoding.
COPY_OK = {
    "mp4": ({"h264", "hevc", "av1"}, {"aac", "mp3"}),
    "mov": ({"h264", "hevc", "prores"}, {"aac", "mp3", "pcm_s16le", "alac"}),
    "mkv": ({"h264", "hevc", "vp8", "vp9", "av1", "mpeg4"},
            {"aac", "mp3", "opus", "vorbis", "flac", "ac3", "eac3", "pcm_s16le"}),
    "webm": ({"vp8", "vp9", "av1"}, {"opus", "vorbis"}),
}

EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"


# ------------------------------------------------------------------ plumbing

def _tools(ctx):
    ffmpeg = find_ffmpeg(ctx.settings.ffmpeg_path)
    if not ffmpeg:
        raise ConversionError("FFmpeg is not installed. Run: winget install Gyan.FFmpeg")
    return ffmpeg, find_ffprobe(ffmpeg)


def _parse_probe(text: str) -> dict:
    info = {"duration": 0.0, "video": None, "audio": None, "width": 0, "height": 0,
            "fps": 25.0, "rate": 0, "channels": 0}
    data = json.loads(text or "{}")
    try:
        info["duration"] = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        pass
    for s in data.get("streams", []):
        kind = s.get("codec_type")
        attached = s.get("disposition", {}).get("attached_pic") == 1
        if kind == "video" and not attached and not info["video"]:
            info["video"] = s.get("codec_name")
            info["width"] = int(s.get("width") or 0)
            info["height"] = int(s.get("height") or 0)
            num, _, den = (s.get("avg_frame_rate") or "25/1").partition("/")
            try:
                info["fps"] = float(num) / float(den or 1) or 25.0
            except (ValueError, ZeroDivisionError):
                pass
        elif kind == "audio" and not info["audio"]:
            info["audio"] = s.get("codec_name")
            info["rate"] = int(s.get("sample_rate") or 0)
            info["channels"] = int(s.get("channels") or 0)
    return info


PROBE_ARGS = ["-v", "error", "-print_format", "json", "-show_format", "-show_streams"]


def probe(ctx, path: Path) -> dict:
    _, ffprobe = _tools(ctx)
    if not ffprobe:
        return _parse_probe("{}")
    return _parse_probe(ctx.run([ffprobe, *PROBE_ARGS, path], capture=True))


def ffmpeg(ctx, src, out: Path, args: list, duration: float, pre: list = (), inputs: list = ()) -> None:
    """Run FFmpeg on src (plus extra inputs) into out, reporting progress."""
    exe, _ = _tools(ctx)

    def on_line(line: str):
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and duration > 0:
            ctx.progress(int(value) / 1e6 / duration * 0.99)

    ctx.run([exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
             "-progress", "pipe:1", "-n", *pre, "-i", src, *inputs, *args, out], on_line=on_line)


def _need(info, kind, src):
    if not info[kind]:
        what = "sound" if kind == "audio" else "video picture"
        raise ConversionError(f"{src.name} has no {what} to convert.")


def audio_ext(path: Path) -> str:
    """The format to write when a tool keeps the audio file's own format."""
    ext = AUDIO_ALIAS.get(ext_of(path), ext_of(path))
    return ext if ext in AUDIO_CODEC else "mp3"


# Quick helpers for the editors (no job context, short and synchronous).

def _quick(cmd: list, timeout: float = 60) -> bytes:
    done = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)
    if done.returncode != 0:
        tail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ConversionError(tail[-1] if tail else "FFmpeg failed")
    return done.stdout


def _exe(custom: str = ""):
    ffmpeg = find_ffmpeg(custom)
    if not ffmpeg:
        raise ConversionError("FFmpeg is not installed. Run: winget install Gyan.FFmpeg")
    return ffmpeg, find_ffprobe(ffmpeg)


def info(path: Path, custom: str = "") -> dict:
    _, ffprobe = _exe(custom)
    return _parse_probe(_quick([ffprobe, *PROBE_ARGS, path]).decode("utf-8", "replace"))


def frame_png(path: Path, t: float, width: int = 960, custom: str = "") -> bytes:
    ffmpeg, _ = _exe(custom)
    scale = f"scale='min({width},iw)':-2" if width else "null"
    return _quick([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.3f}", "-i", path,
                   "-frames:v", "1", "-vf", scale, "-f", "image2pipe", "-vcodec", "png", "-"])


def strip_png(path: Path, duration: float, count: int = 12, height: int = 56, custom: str = "") -> bytes:
    ffmpeg, _ = _exe(custom)
    rate = count / max(0.5, duration)
    return _quick([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-vf",
                   f"fps={rate:.5f},scale=-2:{height},tile={count}x1", "-frames:v", "1",
                   "-f", "image2pipe", "-vcodec", "png", "-"], timeout=120)


def waveform_png(path: Path, width: int = 1400, height: int = 180, color: str = "#FFFFFF",
                 custom: str = "") -> bytes:
    ffmpeg, _ = _exe(custom)
    return _quick([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-filter_complex",
                   f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors={color}",
                   "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], timeout=120)


def preview_wav(path: Path, start: float, end: float, af: str = "", graph: tuple | None = None,
                custom: str = "") -> Path:
    """A short WAV of a section (at most a minute), for listening in an editor.
    af is a simple filter chain; graph is (filter_complex, output label)."""
    ffmpeg, _ = _exe(custom)
    out = Path(tempfile.gettempdir()) / "spinvert-preview.wav"
    length = max(0.1, min(60.0, end - start))
    if graph:
        filters = ["-filter_complex", graph[0], "-map", f"[{graph[1]}]"]
    else:
        filters = ["-vn", *(["-af", af] if af else [])]
    _quick([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            "-i", path, *filters, "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", out])
    return out


def silence_edges(path: Path, custom: str = "") -> tuple[float, float]:
    """Where the sound starts and ends, skipping silence at both ends."""
    ffmpeg, _ = _exe(custom)
    duration = info(path, custom)["duration"]
    done = subprocess.run([str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
                           "silencedetect=n=-45dB:d=0.25", "-f", "null", "-"],
                          capture_output=True, timeout=600, creationflags=CREATE_NO_WINDOW)
    text = done.stderr.decode("utf-8", "replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", text)]
    start, end = 0.0, duration
    if starts and starts[0] <= 0.05 and ends:
        start = ends[0]
    if starts and (len(ends) < len(starts) or ends[-1] >= duration - 0.05):
        end = starts[-1]
    return start, max(start + 0.1, end)


def loudness(path: Path, custom: str = "") -> dict:
    """Measured loudness: input_i (LUFS), input_tp, input_lra."""
    ffmpeg, _ = _exe(custom)
    done = subprocess.run([str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
                           "loudnorm=print_format=json", "-f", "null", "-"],
                          capture_output=True, timeout=600, creationflags=CREATE_NO_WINDOW)
    return _loudnorm_json(done.stderr.decode("utf-8", "replace"))


def _loudnorm_json(text: str) -> dict:
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.S)
    if not match:
        raise ConversionError("Couldn't measure the loudness.")
    return json.loads(match.group(0))


# ------------------------------------------------------------- conversions

def audio_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        info_ = probe(ctx, src)
        _need(info_, "audio", src)
        out = ctx.output(src.stem, ext)
        ffmpeg(ctx, src, out, ["-map", "0:a:0", "-vn", *AUDIO_CODEC[ext]], info_["duration"])
        return [out]
    return run


def _video_only(ext: str, settings) -> list:
    """Video encoder arguments for a container."""
    if ext == "webm":
        return ["-c:v", "libvpx-vp9", "-crf", str(settings.vp9_crf), "-b:v", "0",
                "-deadline", "good", "-cpu-used", "5", "-row-mt", "1"]
    if ext == "avi":
        return ["-c:v", "libxvid", "-q:v", "4"]
    if ext == "wmv":
        return ["-c:v", "wmv2", "-q:v", "3"]
    args = ["-c:v", "libx264", "-preset", "fast", "-crf", str(settings.crf), "-pix_fmt", "yuv420p"]
    if ext in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    return args


def _audio_for(ext: str) -> list:
    """Audio encoder arguments that fit a video container."""
    return {"webm": ["-c:a", "libopus", "-b:a", "128k"], "avi": ["-c:a", "libmp3lame", "-q:a", "4"],
            "wmv": ["-c:a", "wmav2", "-b:a", "192k"]}.get(ext, ["-c:a", "aac", "-b:a", "192k"])


def _encode(ext: str, settings) -> list:
    """Re-encode video and audio for a container (no stream copy)."""
    return _video_only(ext, settings) + _audio_for(ext)


def _keep_audio(ext: str, info_: dict) -> list:
    """Copy the audio when the container takes it as it is, else re-encode it."""
    _, acodecs = COPY_OK.get(ext, (set(), set()))
    return ["-c:a", "copy"] if info_["audio"] in acodecs else _audio_for(ext)


def _tool_ext(src: Path) -> str:
    """Video tools keep MP4, MOV, MKV and WebM; other containers become MP4."""
    ext = ext_of(src)
    return ext if ext in ("mp4", "mov", "mkv", "webm") else "mp4"


def _video_args(ext: str, info_: dict, settings) -> list:
    vcodecs, acodecs = COPY_OK.get(ext, (set(), set()))
    maps = ["-map", "0:v:0", "-map", "0:a:0?"]
    if info_["video"] in vcodecs and (info_["audio"] is None or info_["audio"] in acodecs):
        args = [*maps, "-c", "copy"]
        if ext == "mp4" and info_["video"] == "hevc":
            args += ["-tag:v", "hvc1"]
        if ext in ("mp4", "mov"):
            args += ["-movflags", "+faststart"]
        return args
    return [*maps, "-vf", EVEN, *_encode(ext, settings)]


def video_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        info_ = probe(ctx, src)
        _need(info_, "video", src)
        out = ctx.output(src.stem, ext)
        ffmpeg(ctx, src, out, _video_args(ext, info_, ctx.settings), info_["duration"])
        return [out]
    return run


def video_to_gif(ctx):
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    out = ctx.output(src.stem, "gif")
    graph = ("fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];"
             "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-vf", graph, "-an", "-loop", "0"], info_["duration"])
    return [out]


# ---------------------------------------------------------------- tools

def _target_bytes(params: dict, size: int) -> int | None:
    if params.get("mode") == "size" and params.get("target_mb"):
        return int(float(params["target_mb"]) * 1_000_000)
    if params.get("mode") == "percent":
        return int(size * (1 - float(params.get("percent", 50)) / 100))
    return None


def compress_video(ctx):
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    p = ctx.params
    out = ctx.output(f"{src.stem} (compressed)", "mp4")
    max_w = int(p.get("max_width") or 1920)
    vf = f"scale='trunc(min({max_w},iw)/2)*2':-2"
    target = _target_bytes(p, src.stat().st_size)
    if target:
        audio_kbps = 96 if info_["audio"] else 0
        total_kbps = target * 8 / 1000 / max(1.0, info_["duration"]) * 0.96
        video_kbps = int(total_kbps - audio_kbps)
        if video_kbps < 80:
            raise ConversionError("That size is too small for a video this long.")
        rate = ["-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.4)}k",
                "-bufsize", f"{video_kbps * 2}k"]
    else:
        crf = {"high": 23, "balanced": 28, "small": 32}.get(p.get("quality", "balanced"), 28)
        rate = ["-crf", str(crf)]
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-map", "0:a:0?", "-vf", vf, "-c:v", "libx264",
                           "-preset", "medium", *rate, "-pix_fmt", "yuv420p", "-c:a", "aac",
                           "-b:a", "96k", "-movflags", "+faststart"], info_["duration"])
    if out.stat().st_size >= src.stat().st_size:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def compress_audio(ctx):
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "audio", src)
    p = ctx.params
    ext = audio_ext(src)
    if ext not in LOSSY_KBPS:
        ext = "mp3"  # lossless formats get smaller as MP3
    target = _target_bytes(p, src.stat().st_size)
    if target:
        kbps = int(target * 8 / 1000 / max(1.0, info_["duration"]) * 0.97)
        if kbps < 24:
            raise ConversionError("That size is too small for audio this long.")
    else:
        kbps = int(p.get("kbps", 128))
    out = ctx.output(f"{src.stem} (compressed)", ext)
    ffmpeg(ctx, src, out, ["-map", "0:a:0", "-vn", "-c:a", LOSSY_KBPS[ext], "-b:a", f"{min(kbps, 320)}k"],
           info_["duration"])
    if out.stat().st_size >= src.stat().st_size:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def remove_audio(ctx):
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    out = ctx.output(f"{src.stem} (no sound)", ext_of(src))
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-c", "copy", "-an"], info_["duration"])
    return [out]


def normalize_audio(ctx):
    """Two passes, like a mastering engineer: measure, then correct exactly."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "audio", src)
    p = ctx.params
    target, tp, lra = float(p.get("target", -16)), float(p.get("true_peak", -1.5)), float(p.get("lra", 11))
    exe, _ = _tools(ctx)
    measured = _loudnorm_json(ctx.run([exe, "-hide_banner", "-nostdin", "-i", src, "-vn", "-af",
                                       f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json",
                                       "-f", "null", "-"], stderr=True))
    ctx.progress(0.45)
    graph = (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={measured['input_i']}:"
             f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
             f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
    if info_["video"]:
        ext = ext_of(src)
        out = ctx.output(f"{src.stem} (normalized)", ext)
        args = ["-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", graph,
                "-ar", str(info_["rate"] or 48000), *_audio_for(ext)]
    else:
        ext = audio_ext(src)
        out = ctx.output(f"{src.stem} (normalized)", ext)
        args = ["-map", "0:a:0", "-vn", "-af", graph, "-ar", str(info_["rate"] or 48000), *AUDIO_CODEC[ext]]
    ffmpeg(ctx, src, out, args, info_["duration"])
    return [out]


def trim(ctx):
    """Keep start..end. Audio can fade in and out."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    p = ctx.params
    start = max(0.0, float(p.get("start", 0)))
    end = min(info_["duration"] or 1e9, float(p.get("end", min(info_["duration"], start + 5) or 5)))
    if end - start < 0.05:
        raise ConversionError("The selection is empty.")
    length = end - start
    fade_in, fade_out = float(p.get("fade_in", 0)), float(p.get("fade_out", 0))
    fades = []
    if fade_in > 0:
        fades.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        fades.append(f"afade=t=out:st={max(0, length - fade_out):.3f}:d={fade_out:.3f}")
    pre = ["-ss", f"{start:.3f}", "-t", f"{length:.3f}"]
    if info_["video"]:
        ext = ext_of(src)
        out = ctx.output(f"{src.stem} (trimmed)", ext)
        if p.get("fast"):
            args = ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy"]
        else:
            args = ["-map", "0:v:0", "-map", "0:a:0?", "-vf", EVEN, *_encode(ext, ctx.settings)]
            if fades:
                args += ["-af", ",".join(fades)]
    else:
        _need(info_, "audio", src)
        ext = audio_ext(src)
        out = ctx.output(f"{src.stem} (trimmed)", ext)
        args = ["-map", "0:a:0", "-vn", *(["-af", ",".join(fades)] if fades else []), *AUDIO_CODEC[ext]]
    ffmpeg(ctx, src, out, args, length, pre=pre)
    return [out]


def _box(rect, width: int, height: int):
    """Fractions to an even-sized pixel box inside the frame."""
    x0, y0, x1, y1 = rect
    x, y = int(x0 * width) // 2 * 2, int(y0 * height) // 2 * 2
    w = max(2, int((x1 - x0) * width) // 2 * 2)
    h = max(2, int((y1 - y0) * height) // 2 * 2)
    return x, y, min(w, width - x), min(h, height - y)


def crop_video(ctx):
    """Reframe: keep a rectangle (e.g. 9:16 for Reels), optionally at an exact size."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    p = ctx.params
    rect = p.get("rect") or _centered(info_["width"], info_["height"], 9 / 16)
    x, y, w, h = _box(rect, info_["width"], info_["height"])
    vf = f"crop={w}:{h}:{x}:{y}"
    size = p.get("size")
    if size:
        vf += f",scale={int(size[0]) // 2 * 2}:{int(size[1]) // 2 * 2}:flags=lanczos"
    vf += ",setsar=1"
    ext = _tool_ext(src)
    out = ctx.output(f"{src.stem} (cropped)", ext)
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-map", "0:a:0?", "-vf", vf, *_video_only(ext, ctx.settings),
                           *_keep_audio(ext, info_)], info_["duration"])
    return [out]


def _x264(ctx) -> list:
    return ["-c:v", "libx264", "-preset", "fast", "-crf", str(ctx.settings.crf), "-pix_fmt", "yuv420p"]


def _centered(width: int, height: int, aspect: float):
    """The biggest centred rectangle with this width/height ratio, as fractions."""
    if not width or not height:
        return (0, 0, 1, 1)
    if width / height > aspect:
        w = height * aspect / width
        return ((1 - w) / 2, 0, (1 + w) / 2, 1)
    h = width / aspect / height
    return (0, (1 - h) / 2, 1, (1 + h) / 2)


def _atempo(speed: float) -> str:
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def change_speed(ctx):
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    p = ctx.params
    speed = float(p.get("speed", 2.0))
    if speed <= 0:
        raise ConversionError("Speed must be above zero.")
    label = f"{speed:g}x"
    rate = info_["rate"] or 48000
    af = _atempo(speed) if p.get("keep_pitch", True) else f"asetrate={rate * speed:.0f},aresample={rate}"
    if info_["video"]:
        ext = _tool_ext(src)
        out = ctx.output(f"{src.stem} ({label})", ext)
        args = ["-map", "0:v:0", "-vf", f"setpts=PTS/{speed},{EVEN}", *_video_only(ext, ctx.settings)]
        args += ["-map", "0:a:0", "-af", af, *_audio_for(ext)] if info_["audio"] else ["-an"]
    else:
        _need(info_, "audio", src)
        ext = audio_ext(src)
        out = ctx.output(f"{src.stem} ({label})", ext)
        args = ["-map", "0:a:0", "-vn", "-af", af, *AUDIO_CODEC[ext]]
    ffmpeg(ctx, src, out, args, info_["duration"] / speed)
    return [out]


def save_frames(ctx):
    """Full-resolution PNGs: at chosen times, or one every N seconds."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    p = ctx.params
    folder = ctx.output_dir(f"{src.stem} frames")
    exe, _ = _tools(ctx)
    every = p.get("every")
    if every:
        ffmpeg(ctx, src, folder / f"{src.stem} %04d.png", ["-vf", f"fps=1/{float(every)}"], info_["duration"])
        return [folder]
    times = p.get("times") or [info_["duration"] / 2]
    for i, t in enumerate(times, 1):
        ctx.check()
        stamp = f"{int(t // 3600):02d}-{int(t % 3600 // 60):02d}-{t % 60:06.3f}".replace(".", "_")
        ctx.run([exe, "-hide_banner", "-loglevel", "error", "-n", "-ss", f"{t:.3f}", "-i", src,
                 "-frames:v", "1", folder / f"{src.stem} {stamp}.png"])
        ctx.progress(i / len(times))
    return [folder]


def split_media(ctx):
    """Cut into clips: equal parts, every N seconds, or at chosen points."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    duration = info_["duration"]
    p = ctx.params
    mode = p.get("mode", "parts")
    if mode == "every":
        step = max(0.5, float(p.get("every", 60)))
        points = [i * step for i in range(1, int(duration // step) + 1) if i * step < duration - 0.05]
    elif mode == "points":
        points = sorted(t for t in p.get("points", []) if 0.05 < t < duration - 0.05)
    else:
        parts = max(2, int(p.get("parts", 2)))
        points = [duration * i / parts for i in range(1, parts)]
    if not points:
        raise ConversionError("No cut points inside this file.")
    edges = [0.0, *points, duration]
    folder = ctx.output_dir(f"{src.stem} parts")
    video = bool(info_["video"])
    ext = ext_of(src) if video else audio_ext(src)
    digits = len(str(len(edges) - 1))
    for i, (a, b) in enumerate(zip(edges, edges[1:]), 1):
        ctx.check()
        out = folder / f"{src.stem} part {i:0{digits}d}.{ext}"
        if video:
            args = ["-map", "0:v:0", "-map", "0:a:0?", *(["-c", "copy"] if p.get("fast")
                                                         else ["-vf", EVEN, *_encode(ext, ctx.settings)])]
        else:
            args = ["-map", "0:a:0", "-vn", *AUDIO_CODEC[ext]]
        sub = _Sub(ctx, (i - 1) / (len(edges) - 1), 1 / (len(edges) - 1))
        ffmpeg(sub, src, out, args, b - a, pre=["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}"])
    return [folder]


class _Sub:
    """A context view whose progress maps into a slice of the parent's."""

    def __init__(self, ctx, offset: float, span: float):
        self._ctx, self._offset, self._span = ctx, offset, span

    def progress(self, f: float):
        self._ctx.progress(self._offset + f * self._span)

    def __getattr__(self, name):
        return getattr(self._ctx, name)


def join_media(ctx):
    """Combine clips into one MP4 on the first clip's canvas (or one audio file)."""
    files = [ctx.inputs[i] for i in ctx.params.get("order", [])] or sorted(ctx.inputs, key=natural_key)
    infos = [probe(ctx, f) for f in files]
    total = sum(i["duration"] for i in infos)
    exe, _ = _tools(ctx)
    inputs, graph, labels = [], [], []
    if all(i["video"] for i in infos):
        first = infos[0]
        W, H = first["width"] // 2 * 2, first["height"] // 2 * 2
        fps = round(first["fps"] or 30, 3)
        extra = 0
        for n, (f, inf) in enumerate(zip(files, infos)):
            inputs += ["-i", f]
        silent = []
        for n, inf in enumerate(infos):
            graph.append(f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                         f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{n}]")
            if inf["audio"]:
                graph.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{n}]")
            else:
                silent.append((n, inf["duration"]))
        for n, dur in silent:
            idx = len(files) + extra
            inputs += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            graph.append(f"[{idx}:a]anull[a{n}]")
            extra += 1
        labels = "".join(f"[v{n}][a{n}]" for n in range(len(files)))
        graph.append(f"{labels}concat=n={len(files)}:v=1:a=1[v][a]")
        out = ctx.output("Joined", "mp4", folder=files[0].parent)
        args = ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
                *_x264(ctx), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    elif not any(i["video"] for i in infos):
        for f in files:
            inputs += ["-i", f]
        for n in range(len(files)):
            graph.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{n}]")
        graph.append("".join(f"[a{n}]" for n in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[a]")
        ext = audio_ext(files[0])
        out = ctx.output("Joined", ext, folder=files[0].parent)
        args = ["-filter_complex", ";".join(graph), "-map", "[a]", *AUDIO_CODEC[ext]]
    else:
        raise ConversionError("Join either videos or audio files, not both at once.")
    # The first file is passed as the main input; the rest go in `inputs`.
    ffmpeg(ctx, files[0], out, args, total, inputs=inputs[2:])
    return [out]


def redact_video(ctx):
    """Blur, pixelate or cover areas, each for its own time range."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "video", src)
    W, H = info_["width"], info_["height"]
    areas = ctx.params.get("areas") or [{"rect": (0.35, 0.35, 0.65, 0.65), "style": "blur"}]
    graph, current = [], "0:v"
    for n, area in enumerate(areas):
        x, y, w, h = _box(area["rect"], W, H)
        start, end = float(area.get("start", 0)), float(area.get("end", info_["duration"] or 1e9))
        when = f"between(t,{start:.3f},{end:.3f})"
        style = area.get("style", "blur")
        if style == "solid":
            color = area.get("color", "#000000").lstrip("#")
            graph.append(f"[{current}]drawbox=x={x}:y={y}:w={w}:h={h}:color=0x{color}@1:t=fill:"
                         f"enable='{when}'[s{n}]")
        else:
            if style == "pixelate":
                effect = f"scale={max(2, w // 16)}:{max(2, h // 16)},scale={w}:{h}:flags=neighbor"
            else:
                radius = max(1, min(40, min(w, h) // 4 - 1))
                effect = f"boxblur=luma_radius={radius}:luma_power=3"
            graph.append(f"[{current}]split[b{n}][t{n}];[t{n}]crop={w}:{h}:{x}:{y},{effect}[e{n}];"
                         f"[b{n}][e{n}]overlay={x}:{y}:enable='{when}'[s{n}]")
        current = f"s{n}"
    ext = _tool_ext(src)
    out = ctx.output(f"{src.stem} (redacted)", ext)
    ffmpeg(ctx, src, out, ["-filter_complex", ";".join(graph), "-map", f"[{current}]", "-map", "0:a:0?",
                           *_video_only(ext, ctx.settings), *_keep_audio(ext, info_)], info_["duration"])
    return [out]


def channels_graph(mode: str, left: float, right: float, stereo_in: bool) -> str:
    """The pan filter for mono, stereo, left, right or swap, with a gain per channel."""
    L, R = ("c0", "c1") if stereo_in else ("c0", "c0")
    if mode == "mono":
        return f"pan=mono|c0={left * 0.5:.3f}*{L}+{right * 0.5:.3f}*{R}" if stereo_in else f"pan=mono|c0={left:.3f}*c0"
    if mode == "left":
        return f"pan=mono|c0={left:.3f}*{L}"
    if mode == "right":
        return f"pan=mono|c0={right:.3f}*{R}"
    if mode == "swap":
        return f"pan=stereo|c0={left:.3f}*{R}|c1={right:.3f}*{L}"
    return f"pan=stereo|c0={left:.3f}*{L}|c1={right:.3f}*{R}"


def channels(ctx):
    """mono, stereo, left, right or swap; with a volume per channel."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "audio", src)
    p = ctx.params
    mode = p.get("mode", "mono")
    graph = channels_graph(mode, float(p.get("left", 100)) / 100, float(p.get("right", 100)) / 100,
                           info_["channels"] >= 2)
    label = {"mono": "mono", "left": "left channel", "right": "right channel", "swap": "swapped",
             "stereo": "stereo"}.get(mode, mode)
    if info_["video"]:
        ext = _tool_ext(src)
        out = ctx.output(f"{src.stem} ({label})", ext)
        args = ["-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", graph, *_audio_for(ext)]
    else:
        ext = audio_ext(src)
        out = ctx.output(f"{src.stem} ({label})", ext)
        args = ["-map", "0:a:0", "-vn", "-af", graph, *AUDIO_CODEC[ext]]
    ffmpeg(ctx, src, out, args, info_["duration"])
    return [out]


def bleep_graph(ranges, rate: int, duration: float, tone: str = "beep", frequency: int = 1000):
    """(filter graph, output label): mute the ranges and, unless tone is 'silence',
    put a sine tone in their place."""
    inside = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)
    muted = f"[0:a]volume=enable='{inside}':volume=0[m]"
    if tone == "silence":
        return muted, "m"
    return (f"{muted};sine=frequency={int(frequency)}:sample_rate={rate}:duration={duration:.3f},volume=0.35,"
            f"volume=enable='not({inside})':volume=0[b];[m][b]amix=inputs=2:duration=first:normalize=0[o]", "o")


def bleep(ctx):
    """Replace time ranges with a tone (or silence)."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "audio", src)
    p = ctx.params
    ranges = [r for r in p.get("ranges") or [[1.0, 2.0]] if r[1] > r[0]]
    if not ranges:
        raise ConversionError("Mark at least one part to bleep.")
    duration = info_["duration"]
    graph, last = bleep_graph(ranges, info_["rate"] or 48000, duration, p.get("tone", "beep"),
                              p.get("frequency", 1000))
    if info_["video"]:
        ext = _tool_ext(src)
        out = ctx.output(f"{src.stem} (bleeped)", ext)
        args = ["-filter_complex", graph, "-map", "0:v:0", "-map", f"[{last}]", "-c:v", "copy",
                *_audio_for(ext)]
    else:
        ext = audio_ext(src)
        out = ctx.output(f"{src.stem} (bleeped)", ext)
        args = ["-filter_complex", graph, "-map", f"[{last}]", *AUDIO_CODEC[ext]]
    ffmpeg(ctx, src, out, args, duration)
    return [out]


VISUALIZER_SIZES = {"Landscape": (1920, 1080), "Portrait": (1080, 1920), "Square": (1080, 1080)}


def visualize(ctx):
    """An MP4 of the audio: an animated waveform or bars over a colour or image."""
    src = ctx.inputs[0]
    info_ = probe(ctx, src)
    _need(info_, "audio", src)
    p = ctx.params
    W, H = VISUALIZER_SIZES.get(p.get("size", "Square"), (1080, 1080))
    color = p.get("color", "#FFFFFF").lstrip("#")
    style = p.get("style", "wave")
    bg_image = p.get("image")
    inputs, graph = [], []
    if bg_image and Path(bg_image).is_file():
        inputs = ["-loop", "1", "-i", bg_image]
        graph.append(f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30[bg]")
    else:
        background = p.get("background", "#16161D").lstrip("#")
        graph.append(f"color=c=0x{background}:s={W}x{H}:r=30[bg]")
    wave_h = H // 3
    if style == "bars":
        graph.append(f"[0:a]showfreqs=s={W - 160}x{wave_h}:mode=bar:fscale=log:ascale=sqrt:"
                     f"colors=0x{color}|0x{color}[w]")
    elif style == "still":
        graph.append("[bg]null[out]")
    else:
        graph.append(f"[0:a]showwaves=s={W - 160}x{wave_h}:mode=cline:rate=30:colors=0x{color}[w]")
    if style != "still":
        graph.append("[bg][w]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[out]")
    out = ctx.output(f"{src.stem} (visualizer)", "mp4")
    args = ["-filter_complex", ";".join(graph), "-map", "[out]", "-map", "0:a:0", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart"]
    if style == "still":
        args[args.index("-preset"):args.index("-preset")] = ["-tune", "stillimage"]
    ffmpeg(ctx, src, out, args, info_["duration"], inputs=inputs)
    return [out]
