#!/usr/bin/env python3
"""Compress images, gifs, video, and audio to a target file size using ffmpeg."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
GIF_EXTS = {'.gif'}
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}
VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.wmv'}
LOSSLESS_AUDIO_EXTS = {'.wav', '.flac'}

SIZE_RE = re.compile(r'(?i)^(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?$')
SIZE_UNITS = {'': 1, 'k': 1024, 'm': 1024 ** 2, 'g': 1024 ** 3, 't': 1024 ** 4}


def parse_size(s: str) -> int:
    m = SIZE_RE.match(s.strip())
    if not m:
        raise ValueError(f"invalid size {s!r}, expected e.g. 10mb, 1gb, 3kb, 500k")
    return int(float(m.group(1)) * SIZE_UNITS[m.group(2).lower()])


def categorize(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in GIF_EXTS:
        return 'gif'
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in VIDEO_EXTS:
        return 'video'
    raise ValueError(f"unrecognized file extension {ext!r}")


def default_output_path(input_path: Path, category: str) -> Path:
    ext = input_path.suffix.lower()
    if category == 'audio' and ext in LOSSLESS_AUDIO_EXTS:
        ext = '.mp3'  # lossless formats can't be bitrate-targeted, fall back to mp3
    elif category == 'image' and ext == '.png':
        ext = '.jpg'  # png has no useful quality knob for arbitrary size targets
    return input_path.with_name(f"{input_path.stem}_compressed{ext}")


def require_tools():
    missing = [t for t in ('ffmpeg', 'ffprobe') if shutil.which(t) is None]
    if missing:
        sys.exit(
            "error: missing " + ", ".join(missing) + " on PATH.\nInstall ffmpeg:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg  (or your distro's package manager)\n"
            "  Windows: winget install ffmpeg  (or download from https://ffmpeg.org and add it to PATH)"
        )


def ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def get_duration(path: Path) -> float:
    data = ffprobe_json(path)
    dur = data.get('format', {}).get('duration')
    if dur is None:
        for s in data.get('streams', []):
            if 'duration' in s:
                dur = s['duration']
                break
    if dur is None:
        raise RuntimeError(f"couldn't determine duration of {path}")
    return float(dur)


def has_audio_stream(path: Path) -> bool:
    return any(s['codec_type'] == 'audio' for s in ffprobe_json(path).get('streams', []))


def run_ffmpeg(cmd):
    subprocess.run(cmd, capture_output=True, check=True)


def scale_compress(input_path: Path, output_path: Path, target_bytes: int, vf_fn, extra_args, max_iters=20) -> int:
    """Iteratively shrink dimensions (and whatever vf_fn ties to scale) until under target."""
    scale = 1.0
    size = None
    for _ in range(max_iters):
        cmd = ['ffmpeg', '-y', '-i', str(input_path), '-vf', vf_fn(scale)] + extra_args + [str(output_path)]
        run_ffmpeg(cmd)
        size = output_path.stat().st_size
        if size <= target_bytes or scale < 0.05:
            break
        scale *= 0.85
    return size


def img_vf(scale):
    return f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2"


def gif_vf(scale):
    fps = max(5, int(12 * scale))
    return f"fps={fps},scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2:flags=lanczos"


def image_args(ext):
    if ext in ('.jpg', '.jpeg'):
        return ['-q:v', '4']
    if ext == '.webp':
        return ['-quality', '80']
    return []


def compress_video(input_path: Path, output_path: Path, target_bytes: int) -> int:
    duration = get_duration(input_path)
    budget_bps = target_bytes * 8 * 0.98 / duration

    audio_bitrate = 0
    if has_audio_stream(input_path):
        audio_bitrate = int(max(min(128_000, budget_bps * 0.2), 32_000))
        if audio_bitrate >= budget_bps * 0.9:
            audio_bitrate = 0  # too little budget to bother with an audio track

    video_bitrate = int(max(budget_bps - audio_bitrate, 40_000))

    with tempfile.TemporaryDirectory() as tmp:
        passlog = str(Path(tmp) / "ffmpeg2pass")
        common = ['ffmpeg', '-y', '-i', str(input_path), '-c:v', 'libx264', '-b:v', str(video_bitrate),
                  '-passlogfile', passlog]
        run_ffmpeg(common + ['-pass', '1', '-an', '-f', 'mp4', os.devnull])
        pass2 = common + ['-pass', '2']
        pass2 += ['-c:a', 'aac', '-b:a', str(audio_bitrate)] if audio_bitrate else ['-an']
        run_ffmpeg(pass2 + [str(output_path)])
    return output_path.stat().st_size


AUDIO_CODEC_ARGS = {
    '.mp3': ['-c:a', 'libmp3lame'],
    '.aac': ['-c:a', 'aac'],
    '.m4a': ['-c:a', 'aac'],
    '.ogg': ['-c:a', 'libvorbis'],
    '.opus': ['-c:a', 'libopus'],
}


def compress_audio(input_path: Path, output_path: Path, target_bytes: int) -> int:
    duration = get_duration(input_path)
    bitrate = int(max(min(target_bytes * 8 * 0.97 / duration, 320_000), 8_000))
    codec_args = AUDIO_CODEC_ARGS.get(output_path.suffix.lower(), [])
    run_ffmpeg(['ffmpeg', '-y', '-i', str(input_path)] + codec_args + ['-b:a', str(bitrate), str(output_path)])
    return output_path.stat().st_size


def open_file(path: Path):
    if sys.platform == 'win32':
        os.startfile(path)  # noqa: only exists on windows
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(path)])
    else:
        subprocess.run(['xdg-open', str(path)])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path, help='file to compress')
    ap.add_argument('-s', '--size', required=True, help='target size, e.g. 10mb, 1gb, 3kb, 500k')
    ap.add_argument('-o', '--output', type=Path, help='output path (default: <name>_compressed.<ext>)')
    ap.add_argument('--no-open', action='store_true', help="don't open the result when done")
    args = ap.parse_args()

    require_tools()

    if not args.input.exists():
        sys.exit(f"error: input file not found: {args.input}")
    try:
        target_bytes = parse_size(args.size)
        category = categorize(args.input)
    except ValueError as e:
        sys.exit(f"error: {e}")

    output = args.output or default_output_path(args.input, category)
    if category == 'audio' and output.suffix.lower() in LOSSLESS_AUDIO_EXTS:
        sys.exit(f"error: {output.suffix} is lossless and can't be bitrate-targeted; "
                 f"use .mp3, .aac, .ogg, or .opus instead")

    print(f"compressing {args.input} ({category}) -> {output}  [target {target_bytes:,} bytes]")
    try:
        if category == 'video':
            final_size = compress_video(args.input, output, target_bytes)
        elif category == 'audio':
            final_size = compress_audio(args.input, output, target_bytes)
        elif category == 'gif':
            final_size = scale_compress(args.input, output, target_bytes, gif_vf, ['-loop', '0'])
        else:  # image
            final_size = scale_compress(args.input, output, target_bytes, img_vf,
                                         image_args(output.suffix.lower()))
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors='replace') if e.stderr else str(e)
        sys.exit(f"ffmpeg failed:\n{stderr}")

    if final_size > target_bytes and category in ('gif', 'image'):
        note = "  (hit scale floor, couldn't reach target without unusable quality)"
    elif final_size > target_bytes:
        note = "  (couldn't reach target: bitrate needed is below what the codec can encode cleanly)"
    else:
        note = ""
    print(f"done: {final_size:,} bytes ({final_size / target_bytes * 100:.0f}% of target){note}")

    if not args.no_open:
        open_file(output)


if __name__ == '__main__':
    main()
