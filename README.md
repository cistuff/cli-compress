# cli-compress

Compress images, gifs, video, and audio to a target file size with ffmpeg.

## Requirements

- Python 3.8+
- ffmpeg + ffprobe on PATH
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
  - Windows: `winget install ffmpeg` and add to PATH

## Install

Install from repo:
```
pip install -e .
```

Install from PyPI:
```
pip install cli-compress
```

This gives you a `python -m compress` command on Windows, Linux, and macOS.

## Usage

```
python -m compress input.mp4 -s 10mb
python -m compress photo.png -s 200kb
python -m compress meme.gif -s 3mb
python -m compress song.wav -s 5mb
python -m compress video.mov -s 1gb -o out.mp4
```

- `-s/--size` accepts `kb`, `mb`, `gb` (also `kib`/`mib`/`gib`, same thing) or a raw byte count.
- `-o/--output` is optional; defaults to `<name>_compressed.<ext>`.
- Lossless audio (`.wav`, `.flac`) can't be bitrate-targeted, so it's re-encoded to `.mp3` by default.
- `.png` has no useful quality knob for size targeting, so it's re-encoded to `.jpg` by default.

Video and audio use bitrate math against the clip's duration. Images and gifs
iteratively shrink resolution (and fps, for gifs) until they fit.
