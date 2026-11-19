"""Join caption-aligned excerpts to persona evidence; require real review for release.

Run extract_turns.py first with the registered publisher MP4/VTT. This tool does
not infer face identity, active speaker, or acoustic alignment from a timestamp.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def build(assets=None, review=None):
    spec = read(ROOT / "data/media-selections.json")
    receipt = {x["turn_id"]: x for x in read(ROOT / "results/media-receipt.json")}
    graph = read(ROOT / "data/persona-v2/graph.json")
    reviews = {} if review is None else read(review)
    ids = {x["turn_id"] for x in spec["selections"]}
    if not reviews.keys() <= ids:
        raise ValueError("Review contains unknown turn IDs")
    result = []
    for item in spec["selections"]:
        turn = item["turn_id"]
        recorded = receipt[turn]
        if any(recorded[k] != item[k] for k in ("tag", "start_ms", "end_ms")):
            raise ValueError("Registered timestamp differs from receipt")
        if recorded["evidence_id"] != graph["anchors"][item["tag"]]["evidence_id"]:
            raise ValueError("Turn evidence binding differs from graph")
        files = {}
        for extension, key in (("wav", "wav_sha256"), ("mp4", "video_sha256"), ("txt", "caption_sha256")):
            path = None if assets is None else Path(assets) / f"{turn}.{extension}"
            present = path is not None and path.is_file()
            actual = sha(path) if present else None
            if present and actual != recorded[key]:
                raise ValueError(f"Source bytes changed: {turn}.{extension}")
            files[extension] = {"relative_path": f"{turn}.{extension}", "expected_sha256": recorded[key],
                                "present": present, "sha256_verified": actual == recorded[key] if present else False,
                                "bytes": path.stat().st_size if present else None}
        available = all(f["present"] for f in files.values())
        review_row = reviews.get(turn, {})
        flags = {k: review_row.get(k) is True for k in ("speaker_verified", "visible_speaking_face_verified", "acoustic_alignment_verified")}
        # A review must be bound to these exact bytes and have accountable notes.
        if any(flags.values()):
            if not available or not review_row.get("reviewer") or not review_row.get("reviewed_at") or not review_row.get("notes"):
                raise ValueError(f"Review lacks verified assets or reviewer record: {turn}")
            if review_row.get("video_sha256") != recorded["video_sha256"] or review_row.get("wav_sha256") != recorded["wav_sha256"]:
                raise ValueError("Review references different media")
        if available:
            with wave.open(str(Path(assets) / f"{turn}.wav")) as f:
                expected = (item["end_ms"] - item["start_ms"]) / 1000
                if f.getframerate() != 16000 or f.getnchannels() != 1 or abs(f.getnframes()/16000-expected) > .05:
                    raise ValueError("Unexpected audio format or duration")
        result.append({**item, "event_id": spec["event"], "evidence_id": recorded["evidence_id"],
                       "scope": "caption_excerpt_not_full_answer", "source_url": spec["publisher"],
                       "clock_mapping": {"clip_ms_zero_is_source_ms": item["start_ms"]},
                       "assets": files, "review": {**flags, "record": review_row or None},
                       "multimodal_training_eligible": available and all(flags.values()),
                       "text_graph_eligible": True})
    return {"schema_version": 1, "method": "MCCCD-inspired caption-aligned pilot, not a full collection reproduction",
            "turns": result, "training_eligible_count": sum(x["multimodal_training_eligible"] for x in result),
            "assets_available_count": sum(all(f["present"] for f in x["assets"].values()) for x in result)}


def review_frames(assets, out):
    """Export beginning/middle/end contact frames; human review still required."""
    manifest = build(assets)
    out.mkdir(parents=True, exist_ok=False)
    for row in manifest["turns"]:
        if not row["assets"]["mp4"]["present"]:
            continue
        duration = (row["end_ms"] - row["start_ms"]) / 1000
        for label, fraction in (("start", .1), ("middle", .5), ("end", .9)):
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", str(duration*fraction),
                            "-i", str(Path(assets)/row["assets"]["mp4"]["relative_path"]), "-frames:v", "1",
                            str(out/f'{row["turn_id"]}-{label}.png')], check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets", type=Path)
    p.add_argument("--review", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", type=Path)
    a = p.parse_args()
    if a.out.exists():
        p.error("Use a new output path")
    result = build(a.assets, a.review)
    if a.frames:
        if a.assets is None:
            p.error("--frames requires --assets")
        review_frames(a.assets, a.frames)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("training_eligible_count", "assets_available_count")}))
