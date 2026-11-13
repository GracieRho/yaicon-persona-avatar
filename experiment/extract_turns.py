"""Cut time-aligned WAV, small video and private caption text from publisher files."""

import argparse
import hashlib
import html
import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
TIMING = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})(?:\s.*)?$"
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def millis(value):
    hours, minutes, seconds, ms = map(int, re.split("[:.]", value))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + ms


def cues(path):
    rows = []
    for block in re.split(r"\n[ \t]*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            match = TIMING.fullmatch(line.strip())
            if match:
                caption = html.unescape(
                    re.sub(r"<[^>]+>", "", " ".join(lines[i + 1 :]))
                ).strip()
                rows.append((millis(match[1]), millis(match[2]), caption))
                break
    if not rows:
        raise ValueError("No time-coded WebVTT captions")
    return rows


def select_text(rows, start, end):
    chosen = [(a, b, t) for a, b, t in rows if a < end and b > start]
    if (
        not chosen
        or chosen[0][0] != start
        or chosen[-1][1] != end
        or any(a < start or b > end for a, b, _ in chosen)
    ):
        raise ValueError(
            "Selection must align exactly with complete publisher caption cues"
        )
    return " ".join(t for _, _, t in chosen)


def extract(video, vtt, out):
    spec = json.loads((DATA / "media-selections.json").read_text())
    graph = json.loads((DATA / "persona-graph.json").read_text())
    if digest(video) != spec["video_sha256"] or digest(vtt) != spec["vtt_sha256"]:
        raise ValueError(
            "Input differs from the publisher files registered for these timestamps"
        )
    if out.exists():
        raise FileExistsError(f"Use a new output directory: {out}")
    rows, receipt = cues(vtt), []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "turns"
        stage.mkdir()
        for item in spec["selections"]:
            start, end = item["start_ms"], item["end_ms"]
            caption = select_text(rows, start, end)
            stem = stage / item["turn_id"]
            dur = (end - start) / 1000
            wav, mp4 = stem.with_suffix(".wav"), stem.with_suffix(".mp4")
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-ss",
                f"{start/1000:.3f}",
                "-i",
                str(video),
            ]
            subprocess.run(
                cmd
                + [
                    "-t",
                    f"{dur:.3f}",
                    "-map",
                    "0:a:0",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                    "-t",
                    f"{dur:.3f}",
                    "-map",
                    "0:v:0",
                    "-an",
                    "-vf",
                    "scale=-2:360",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-threads",
                    "2",
                    "-pix_fmt",
                    "yuv420p",
                    str(mp4),
                ],
                check=True,
            )
            stem.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")
            with wave.open(str(wav)) as f:
                samples = f.getnframes()
                if abs(samples / f.getframerate() - dur) > 0.05:
                    raise ValueError("Unexpected audio duration")
            probe = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_frames,duration",
                    "-of",
                    "json",
                    str(mp4),
                ],
                text=True,
            )
            info = json.loads(probe)["streams"][0]
            if int(info["nb_frames"]) < 1 or abs(float(info["duration"]) - dur) > 0.1:
                raise ValueError("Unexpected video duration")
            receipt.append(
                {
                    **item,
                    "evidence_id": graph["anchors"][item["tag"]],
                    "event": spec["event"],
                    "speaker_basis": "publisher text",
                    "speaking_face_verified": False,
                    "acoustically_aligned": False,
                    "samples_16khz": samples,
                    "video_frames": int(info["nb_frames"]),
                    "video_seconds": float(info["duration"]),
                    "wav_sha256": digest(wav),
                    "video_sha256": digest(mp4),
                    "caption_sha256": digest(stem.with_suffix(".txt")),
                }
            )
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        stage.rename(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("video", "vtt", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    extract(args.video, args.vtt, args.out)
