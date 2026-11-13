"""Search local persona evidence and return the matching source and turn."""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from build_cards import DATA, build_cards, json_lines, required_text, searchable

# Short grammatical words alone are weak evidence for a match in an English question.
STOP_WORDS = set("a an and are as at be by can did do does for from he how i in is it of on or she that "
                 "the their there they this to was were what when which who why with would you your "
                 "jensen huang 젠슨 젠슨황 황 어떻게 무엇 어떤".split())
PARTICLES = ("에서는", "으로는", "에서", "에게", "으로", "처럼", "이란", "은", "는", "이", "가",
             "을", "를", "의", "에", "도", "와", "과")


def query_terms(query):
    terms = []
    for word in re.findall(r"[^\W_]+", query.casefold()):
        if word not in STOP_WORDS:
            terms.append(word)
            if re.fullmatch("[가-힣]+", word):
                for particle in PARTICLES:
                    stem = word.removesuffix(particle)
                    if stem != word and len(stem) >= 2:
                        if stem not in STOP_WORDS:
                            terms.append(stem)
                        break
    return list(dict.fromkeys(terms))


def read_built_cards(path):
    cards = {}
    legacy_seeds = None
    for line, row in json_lines(path):
        try:
            key = required_text(row, "evidence_id")
            if key in cards:
                raise ValueError(f"duplicate evidence ID {key}")
            for field in ("source_url", "locator"):
                required_text(row, field)
            # Restore only a known starter card. Unlabelled custom data must go through the builder.
            if "source_split" not in row and "review_status" not in row and "evidence_text" not in row:
                if legacy_seeds is None:
                    legacy_seeds = {c["evidence_id"]: c for c in build_cards(DATA / "turns.jsonl", DATA / "sources.json")
                                    if c["source_split"] == "train" and c["review_status"] == "reviewed" and not c["exchange"]}
                seed = legacy_seeds.get(key)
                if seed is None or row.get("claim_ko") != seed["claim_ko"]:
                    raise ValueError("missing split and review metadata; build this record with build_cards.py")
                row = seed
            for field in ("source_split", "review_status", "evidence_text"):
                required_text(row, field)
            tags = row.get("tags")
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError("invalid tags")
            if row.get("exchange") is not None:
                if not isinstance(row["exchange"], dict):
                    raise ValueError("exchange must be a JSON object")
                for field in ("question", "answer"):
                    required_text(row["exchange"], field)
            cards[key] = row
        except ValueError as exc:
            raise ValueError(f"{path.name}:{line}: {exc}") from exc
    if not cards:
        raise ValueError(f"{path.name}: no cards")
    return list(cards.values())


def search(cards, query, limit):
    words = query_terms(query)
    if not words:
        return []
    available = {c["evidence_id"]: c for c in cards if searchable(c)}
    match_query = " OR ".join(f'"{word}"' for word in words)
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE VIRTUAL TABLE evidence USING fts5(id UNINDEXED, tags, situation, context, body, exchange_text)")
        db.executemany("INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)", (
            (key, " ".join(c["tags"]), c.get("situation"), c.get("context_ko"), c["evidence_text"],
             " ".join((c["exchange"]["question"], c["exchange"]["answer"])) if c.get("exchange") else "")
            for key, c in available.items()
        ))
        rows = db.execute("SELECT id FROM evidence WHERE evidence MATCH ? "
                          "ORDER BY bm25(evidence, 0, 3, 2, 1, 1, 1), id LIMIT ?", (match_query, limit))
        return [available[row[0]] for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="an English or Korean question")
    parser.add_argument("--cards", type=Path, help="JSONL produced by build_cards.py; defaults to the bundled turns")
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    try:
        cards = (read_built_cards(args.cards) if args.cards else
                 build_cards(DATA / "turns.jsonl", DATA / "sources.json"))
        if args.query is None:
            eligible = sum(searchable(c) for c in cards)
            print(f"OK: {len(cards)} unique evidence cards, {eligible} searchable")
            return
        hits = search(cards, args.query, args.limit)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
    fields = ("evidence_id", "evidence_text", "text_provenance", "claim_ko", "response_pattern_ko",
              "source_url", "locator", "published_anchor_s", "exchange")
    print(json.dumps([{key: card.get(key) for key in fields} for card in hits], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
