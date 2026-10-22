"""Audio and video with FFmpeg."""

from __future__ import annotations

import json
from pathlib import Path

from spinvert.util import ConversionError, ext_of, find_ffmpeg, find_ffprobe

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

# Containers that can take these codecs as they are, without re-encoding.
COPY_OK = {
    "mp4": ({"h264", "hevc", "av1"}, {"aac", "mp3"}),
    "mov": ({"h264", "hevc", "prores"}, {"aac", "mp3", "pcm_s16le", "alac"}),
    "mkv": ({"h264", "hevc", "vp8", "vp9", "av1", "mpeg4"},
            {"aac", "mp3", "opus", "vorbis", "flac", "ac3", "eac3", "pcm_s16le"}),
    "webm": ({"vp8", "vp9", "av1"}, {"opus", "vorbis"}),
}

EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"


def _tools(ctx):
    ffmpeg = find_ffmpeg(ctx.settings.ffmpeg_path)
    if not ffmpeg:
        raise ConversionError("FFmpeg is not installed. Run: winget install Gyan.FFmpeg")
    return ffmpeg, find_ffprobe(ffmpeg)


def probe(ctx, path: Path) -> dict:
    _, ffprobe = _tools(ctx)
    info = {"duration": 0.0, "video": None, "audio": None, "width": 0, "rate": 0}
    if not ffprobe:
        return info
    text = ctx.run([ffprobe, "-v", "error", "-print_format", "json",
                    "-show_format", "-show_streams", path], capture=True)
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
        elif kind == "audio" and not info["audio"]:
            info["audio"] = s.get("codec_name")
            info["rate"] = int(s.get("sample_rate") or 0)
    return info


def ffmpeg(ctx, src: Path, out: Path, args: list, duration: float) -> None:
    exe, _ = _tools(ctx)

    def on_line(line: str):
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and duration > 0:
            ctx.progress(int(value) / 1e6 / duration * 0.99)

    ctx.run([exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
             "-progress", "pipe:1", "-n", "-i", src, *args, out], on_line=on_line)


def _need(info, kind, src):
    if not info[kind]:
        what = "sound" if kind == "audio" else "video picture"
        raise ConversionError(f"{src.name} has no {what} to convert.")


def audio_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        info = probe(ctx, src)
        _need(info, "audio", src)
        out = ctx.output(src.stem, ext)
        ffmpeg(ctx, src, out, ["-map", "0:a:0", "-vn", *AUDIO_CODEC[ext]], info["duration"])
        return [out]
    return run


def _video_args(ext: str, info: dict, settings) -> list:
    vcodecs, acodecs = COPY_OK.get(ext, (set(), set()))
    maps = ["-map", "0:v:0", "-map", "0:a:0?"]
    if info["video"] in vcodecs and (info["audio"] is None or info["audio"] in acodecs):
        args = [*maps, "-c", "copy"]
        if ext == "mp4" and info["video"] == "hevc":
            args += ["-tag:v", "hvc1"]
    elif ext == "webm":
        args = [*maps, "-c:v", "libvpx-vp9", "-crf", str(settings.vp9_crf), "-b:v", "0",
                "-deadline", "good", "-cpu-used", "5", "-row-mt", "1",
                "-c:a", "libopus", "-b:a", "128k"]
    elif ext == "avi":
        args = [*maps, "-vf", EVEN, "-c:v", "libxvid", "-q:v", "4",
                "-c:a", "libmp3lame", "-q:a", "4"]
    elif ext == "wmv":
        args = [*maps, "-vf", EVEN, "-c:v", "wmv2", "-q:v", "3",
                "-c:a", "wmav2", "-b:a", "192k"]
    else:
        args = [*maps, "-vf", EVEN, "-c:v", "libx264", "-preset", "fast",
                "-crf", str(settings.crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    if ext in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    return args


def video_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        info = probe(ctx, src)
        _need(info, "video", src)
        out = ctx.output(src.stem, ext)
        ffmpeg(ctx, src, out, _video_args(ext, info, ctx.settings), info["duration"])
        return [out]
    return run


def video_to_gif(ctx):
    src = ctx.inputs[0]
    info = probe(ctx, src)
    _need(info, "video", src)
    out = ctx.output(src.stem, "gif")
    graph = ("fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];"
             "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-vf", graph, "-an", "-loop", "0"], info["duration"])
    return [out]


def compress_video(ctx):
    src = ctx.inputs[0]
    info = probe(ctx, src)
    _need(info, "video", src)
    out = ctx.output(f"{src.stem} (compressed)", "mp4")
    scale = "scale='trunc(min(1920,iw)/2)*2':-2"
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-map", "0:a:0?", "-vf", scale,
                           "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"], info["duration"])
    if out.stat().st_size >= src.stat().st_size:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def remove_audio(ctx):
    src = ctx.inputs[0]
    info = probe(ctx, src)
    _need(info, "video", src)
    out = ctx.output(f"{src.stem} (no sound)", ext_of(src))
    ffmpeg(ctx, src, out, ["-map", "0:v:0", "-c", "copy", "-an"], info["duration"])
    return [out]


def normalize_audio(ctx):
    src = ctx.inputs[0]
    info = probe(ctx, src)
    _need(info, "audio", src)
    ext = ext_of(src)
    ext = {"aac": "m4a", "aif": "aiff", "oga": "ogg"}.get(ext, ext)
    out = ctx.output(f"{src.stem} (normalized)", ext)
    rate = str(info["rate"] or 48000)
    ffmpeg(ctx, src, out, ["-map", "0:a:0", "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                           "-ar", rate, *AUDIO_CODEC.get(ext, AUDIO_CODEC["mp3"])], info["duration"])
    return [out]
