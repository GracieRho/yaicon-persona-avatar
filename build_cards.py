"""Build source-linked Jensen Huang evidence cards from reviewed turns (JSONL)."""
import argparse
import json
import math
import re
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

DATA = Path(__file__).resolve().parent / "data"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")


def required_text(mapping, field):
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"expected text for {field}")
    return value.strip()


def identifier(mapping, field):
    value = required_text(mapping, field)
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def json_lines(path):
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("expected a JSON object")
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
                yield line_number, row


def load_sources(path):
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("sources.json must contain an array")
    sources, event_splits, url_splits = {}, {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("expected a source object")
        key, event = identifier(row, "id"), identifier(row, "source_event_id")
        for field, maximum in (("title", 500), ("publisher", 200), ("source_type", 100)):
            if len(required_text(row, field)) > maximum:
                raise ValueError(f"{key}: {field} exceeds {maximum} characters")
        date.fromisoformat(required_text(row, "published_at"))
        if row.get("recorded_at"):
            date.fromisoformat(required_text(row, "recorded_at"))
        if row.get("timeline") is not None and len(required_text(row, "timeline")) > 100:
            raise ValueError(f"{key}: timeline exceeds 100 characters")
        url = urlsplit(required_text(row, "url"))
        if url.scheme not in {"https", "http"} or not url.hostname:
            raise ValueError(f"{key}: expected an HTTP(S) source URL")
        split = row.get("split")
        if split not in ("train", "validation", "test"):
            raise ValueError(f"{key}: expected train, validation or test")
        if key in sources or event_splits.setdefault(event, split) != split:
            raise ValueError(f"{key}: duplicate source ID or inconsistent split for event {event}")
        params = sorted((k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                        if not k.lower().startswith("utm_") and k.lower() not in {"si", "feature"})
        location = (url.netloc.lower(), url.path.rstrip("/"), tuple(params))
        if url_splits.setdefault(location, split) != split:
            raise ValueError(f"{key}: the same source URL appears in different splits")
        sources[key] = row
    return sources


def make_card(turn, source):
    key = identifier(turn, "evidence_id")
    status = turn.get("review_status", "draft")
    if status not in ("draft", "reviewed"):
        raise ValueError("expected draft or reviewed status")
    tags = turn.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        raise ValueError("tags must be a list of nonempty strings")
    anchor = turn.get("published_anchor_s")
    if anchor is not None and (type(anchor) not in (int, float) or not math.isfinite(anchor)
                               or anchor < 0 or not source.get("timeline")):
        raise ValueError("a publisher anchor needs a nonnegative time and a named timeline")

    exchange = turn.get("exchange")
    if exchange is not None:
        if not isinstance(exchange, dict):
            raise ValueError("exchange must be a JSON object")
        for field in ("questioner", "respondent", "question", "answer"):
            required_text(exchange, field)
        if exchange["respondent"] != "Jensen Huang" or exchange["questioner"] == exchange["respondent"]:
            raise ValueError("check the interviewer and the target speaker")
        if exchange.get("extent") not in ("excerpt", "complete_turn"):
            raise ValueError("specify whether the exchange is a complete turn or an excerpt")
        if exchange["extent"] == "excerpt":
            required_text(exchange, "note")

    claim = required_text(turn, "claim_ko") if "claim_ko" in turn else None
    if claim is None and exchange is None:
        raise ValueError("expected an original exchange or a sourced summary")
    for field in ("context_ko", "response_pattern_ko", "situation"):
        if field in turn:
            required_text(turn, field)
    return {
        "evidence_id": key, "source_id": source["id"], "source_event_id": source["source_event_id"],
        "source_url": source["url"], "published_at": source["published_at"], "source_split": source["split"],
        "source_type": source["source_type"], "review_status": status, "locator": required_text(turn, "locator"),
        "timeline": source.get("timeline"), "published_anchor_s": anchor, "tags": tags,
        "situation": turn.get("situation"), "context_ko": turn.get("context_ko"),
        "claim_ko": claim, "response_pattern_ko": turn.get("response_pattern_ko"), "exchange": exchange,
        "evidence_text": claim if claim is not None else exchange["answer"],
        "text_provenance": "editorial_summary" if claim is not None else "publisher_transcript",
    }


def build_cards(turns_path, sources_path):
    sources = load_sources(sources_path)
    cards = {}
    for line_number, turn in json_lines(turns_path):
        try:
            source_id = identifier(turn, "source_id")
            if source_id not in sources:
                raise ValueError(f"unknown source {source_id}")
            card = make_card(turn, sources[source_id])
            key = card["evidence_id"]
            if key in cards:
                raise ValueError(f"duplicate evidence ID {key}")
            cards[key] = card
        except ValueError as exc:
            raise ValueError(f"{turns_path.name}:{line_number}: {exc}") from exc
    if not cards:
        raise ValueError(f"{turns_path.name}: no turns")
    return list(cards.values())


def searchable(card):
    return card["source_split"] == "train" and card["review_status"] == "reviewed"


def studio_record(card):
    for value, maximum, field in ((card["evidence_id"], 113, "evidence_id"),
                                  (card["locator"], 500, "locator"),
                                  (card["evidence_text"], 12000, "evidence_text"),
                                  (card["tags"], 30, "tags")):
        if len(value) > maximum:
            raise ValueError(f"{card['evidence_id']}: {field} too long for Studio export")
    locator = {"label": card["locator"], "timeline": card["timeline"]}
    if card["published_anchor_s"] is not None:
        locator["start_seconds"] = card["published_anchor_s"]
    is_transcript = card["text_provenance"] == "publisher_transcript"
    return {
        "id": "yaicon-" + card["evidence_id"], "persona_id": "jensen-huang", "source_id": card["source_id"],
        "text": card["evidence_text"], "topics": card["tags"], "situations": [], "locator": locator,
        "kind": "transcript" if is_transcript else "stated_view", "confidence": "source_grounded",
        "text_provenance": card["text_provenance"], "review_status": card["review_status"],
        "projection_eligibility": {"factual": True, "text_style": False, "aligned_speech": False,
                                   "visible_behavior": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=Path, default=DATA / "turns.jsonl")
    parser.add_argument("--sources", type=Path, default=DATA / "sources.json")
    parser.add_argument("--format", choices=["cards", "studio"], default="cards")
    parser.add_argument("-o", "--output", type=Path, help="write UTF-8 JSONL (default: stdout)")
    args = parser.parse_args()
    try:
        cards = build_cards(args.turns, args.sources)
        rows = [studio_record(c) for c in cards if searchable(c)] if args.format == "studio" else cards
        output = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
        if args.output is None:
            print(output, end="")
            return
        if args.output.resolve() in {args.sources.resolve(), args.turns.resolve()}:
            raise ValueError("--output must differ from the two input files")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.write_text(output, encoding="utf-8")
            temporary.replace(args.output)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
