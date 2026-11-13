"""Replay Korean stage questions; optionally generate matched flat/graph model drafts."""

import argparse
import csv
import json
import random
import time
from pathlib import Path

from stage_qa import PILOT, StageQA, model_draft, read_json


def run(cases, qa, model=None, base_url=None):
    rows = []
    for i, case in enumerate(cases):
        answer = qa.answer(case["question"], case.get("previous"))
        sources = [s["id"] for s in answer["sources"]]
        application = any(n["kind"] == "application" for n in answer["sections"])
        ok = (case["route"] == answer["route"] and case["sources"] == sources
              and case.get("application", False) == application)
        row = {"id": case["id"], "question": case["question"], "route": answer["route"],
               "sources": sources, "application": application, "matches": ok,
               "spoken_text": answer["spoken_text"]}
        if case.get("previous"):
            row["previous"] = case["previous"]
        if model and application:
            row["drafts"] = {}
            for surface in (("flat", "graph") if i % 2 == 0 else ("graph", "flat")):
                start = time.monotonic()
                draft = model_draft(answer, base_url, model, surface)
                row["drafts"][surface] = {**draft, "elapsed_s": round(time.monotonic() - start, 2)}
        rows.append(row)
    pairs = [r for r in rows if "drafts" in r]
    return {"questions": len(rows), "exact_route_sources_application": sum(r["matches"] for r in rows),
            "paired_model_questions": len(pairs), "model": model,
            "model_json_format_ok": {k: sum(r["drafts"][k]["format_ok"] for r in pairs)
                                     for k in ("flat", "graph")} if pairs else None,
            "human_persona_fidelity": None, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="A new results file")
    parser.add_argument("--questions", type=Path, default=PILOT / "stage-questions.json")
    parser.add_argument("--model", help="Rehearsal model; omit to check routing only")
    parser.add_argument("--base-url", default="http://127.0.0.1:18731/v1")
    parser.add_argument("--review-dir", type=Path, help="Create a new directory with a blind CSV and separate key")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a new results file")
    if args.review_dir and (not args.model or args.review_dir.exists()):
        parser.error("A blind review needs --model and a new directory")
    report = run(read_json(args.questions), StageQA(), args.model, args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    if args.review_dir:
        write_blind(report, StageQA(), args.review_dir)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))


def write_blind(report, qa, folder):
    rng = random.Random(23)
    key = {}
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / "questions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["id", "이전 질문", "질문", "답변 A", "답변 B", "출처·위치",
                         "A 원문 취지 1–5", "B 원문 취지 1–5", "A 상황 적용 1–5", "B 상황 적용 1–5",
                         "A 잘못 귀속한 주장", "B 잘못 귀속한 주장", "선호 A/B/동률", "메모"])
        for row in report["rows"]:
            if not row.get("drafts"):
                continue
            labels = ["flat", "graph"]
            rng.shuffle(labels)
            key[row["id"]] = labels
            answers = []
            for label in labels:
                draft = row["drafts"][label]
                answers.append(" ".join(draft["parts"]) if draft["format_ok"] else draft["raw"])
            packet = qa.plan(row["question"], row.get("previous"))
            references = "\n".join(f"{s['url']} · {s['locator']}" for s in packet["sources"])
            writer.writerow([row["id"], row.get("previous", ""), row["question"], *answers, references] + [""] * 8)
    (folder / "key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
