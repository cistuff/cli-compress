"""Self-check for the pure logic (size parsing, categorization). No ffmpeg required."""
from pathlib import Path

from compress import parse_size, categorize, default_output_path

assert parse_size("10mb") == 10 * 1024 ** 2
assert parse_size("1gb") == 1024 ** 3
assert parse_size("3kb") == 3 * 1024
assert parse_size("500k") == 500 * 1024
assert parse_size("1.5GB") == int(1.5 * 1024 ** 3)
assert parse_size("2048") == 2048
assert parse_size("10MiB") == 10 * 1024 ** 2
try:
    parse_size("banana")
    assert False, "expected ValueError"
except ValueError:
    pass

assert categorize(Path("clip.mp4")) == 'video'
assert categorize(Path("song.mp3")) == 'audio'
assert categorize(Path("anim.gif")) == 'gif'
assert categorize(Path("photo.JPG")) == 'image'
try:
    categorize(Path("file.txt"))
    assert False, "expected ValueError"
except ValueError:
    pass

assert default_output_path(Path("a.wav"), 'audio').suffix == '.mp3'
assert default_output_path(Path("a.png"), 'image').suffix == '.jpg'
assert default_output_path(Path("a.mp4"), 'video').name == 'a_compressed.mp4'

print("ok")
