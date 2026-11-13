"""Run paired English generation with PR #17's retriever and a source-linked persona graph."""

import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

DATA = Path(__file__).resolve().parent / "data"
UPSTREAM = "3038629f3c4aeefff568684a6a7ba10df2b61db8"
SYSTEM = (
    "Write a short, clearly simulated interview reply inspired by Jensen Huang. "
    "Answer the question in English in one or two sentences. Use only the supplied "
    "relations for any account of his experience or views. Use your own wording, never "
    "a verbatim quote. For grounded claims cite the supplied source with its exact tag, "
    "such as [S1]. When the evidence does not answer the question, say that and do "
    "not invent a detail or citation."
)
TOKEN_LIMIT = 96
PROMPT_LIMIT = 1024
SEED = 23


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs(
    upstream_root,
    graph_path=DATA / "persona-graph.json",
    questions_path=DATA / "questions.json",
):
    folder = upstream_root.resolve()
    sha = subprocess.check_output(
        ["git", "-C", str(folder), "rev-parse", "HEAD"], text=True
    ).strip()
    if sha != UPSTREAM:
        raise ValueError(f"Expected upstream PR #17 commit {UPSTREAM}, found {sha}")
    relevant_paths = ["src/bias", "data/personas/jensen-huang"]
    if subprocess.check_output(
        ["git", "-C", str(folder), "status", "--porcelain", "--", *relevant_paths],
        text=True,
    ).strip():
        raise ValueError("Upstream source or corpus differs from the pinned checkout")
    sys.path.insert(0, str(folder / "src"))
    from bias.corpus import Corpus, source_event_id
    from bias.retrieval import Retriever

    corpus = Corpus.load(folder / "data/personas/jensen-huang")
    graph, questions = read_json(graph_path), read_json(questions_path)
    training = {row.id for row in corpus.training_evidence}
    if not set(graph["anchors"].values()) <= training:
        raise ValueError("Every annotation must reference indexed factual evidence")
    if len(set(graph["anchors"].values())) != len(graph["anchors"]):
        raise ValueError("Evidence IDs must map to unique citation tags")
    for tag, head, relation, tail in graph["edges"]:
        if (
            tag not in graph["anchors"]
            or head not in graph["nodes"]
            or tail not in graph["nodes"]
            or not relation
        ):
            raise ValueError(f"Unknown graph endpoint in {(tag, head, relation, tail)}")
    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)) or not all(
        set(q["expected"]) <= graph["anchors"].keys() for q in questions
    ):
        raise ValueError("Questions must have unique IDs and known reference tags")
    training_events = {
        source_event_id(corpus.sources[corpus.evidence[key].source_id])
        for key in training
    }
    if any(q.get("event") in training_events for q in questions):
        raise ValueError("Held-out event appears in the retrieval corpus")

    return corpus, Retriever(corpus), graph, questions


def paired_evidence(graph, tags):
    """Identical semantic triples, labels and citations in both representations."""
    rows = [
        (tag, graph["nodes"][head], rel, graph["nodes"][tail])
        for tag, head, rel, tail in graph["edges"]
        if tag in tags
    ]
    flat = "\n".join(f"{head} {rel} {tail} [{tag}]" for tag, head, rel, tail in rows)
    adjacency = defaultdict(list)
    for tag, head, relation, tail in rows:
        adjacency[head].append(f"{relation} → {tail} [{tag}]")
    linked = "\n".join(
        f"{head}\n" + "\n".join(f"  → {edge}" for edge in outgoing)
        for head, outgoing in adjacency.items()
    )
    return {
        name: value or "(no eligible evidence)"
        for name, value in (("flat", flat), ("graph", linked))
    }, rows


class LocalChat:
    def __init__(self, base_url, model):
        self.url = base_url.rstrip("/")
        self.model = model
        host = urlsplit(self.url).hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                "This pilot expects a local OpenAI-compatible model server"
            )
        self.http = build_opener(ProxyHandler({}))

    def generate(self, question, evidence):
        prompt = f"Question\n{question}\n\nEvidence\n{evidence}"
        body = {
            "model": self.model,
            "temperature": 0,
            "seed": SEED,
            "max_tokens": TOKEN_LIMIT,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        req = Request(
            self.url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        start = time.monotonic()
        with self.http.open(req, timeout=180) as result:
            answer = json.load(result)
        used = answer["usage"]
        if used["prompt_tokens"] > PROMPT_LIMIT:
            raise ValueError(
                "Prompt exceeds the registered budget; both conditions must use every selected triple"
            )
        choice = answer["choices"][0]
        return {
            "answer": choice["message"]["content"].strip(),
            "prompt_tokens": used["prompt_tokens"],
            "output_tokens": used["completion_tokens"],
            "finish_reason": choice["finish_reason"],
            "seconds": round(time.monotonic() - start, 3),
            "runtime": answer.get("system_fingerprint"),
            "prompt_sha256": hashlib.sha256(
                json.dumps(body, sort_keys=True).encode()
            ).hexdigest(),
        }


def tag_check(answer, available, expected):
    """Mechanical source-tag checks, never a semantic or personality rating."""
    cited = re.findall(r"\[([^\[\]\n]{1,80})\]", answer)
    return {
        "cited": cited,
        "out_of_packet": sorted(set(cited) - set(available)),
        "expected_citation": bool(set(cited) & set(expected)),
    }


def blind_sheet(rows, questions, out):
    idx = {(r["id"], r["condition"]): r for r in rows}
    rng = random.Random(SEED)
    key = {}
    with (out / "blind-review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "question",
                "A",
                "B",
                "source_or_reference",
                "value_fidelity_A_1_5",
                "value_fidelity_B_1_5",
                "unsupported_claims_A",
                "unsupported_claims_B",
                "preference_A_B_tie",
                "notes",
            ]
        )
        for q in questions:
            names = ["flat", "graph"]
            rng.shuffle(names)
            key[q["id"]] = names
            first, second = (idx[q["id"], n] for n in names)
            sources = list(dict.fromkeys(h["url"] for h in first["annotated_sources"]))
            writer.writerow(
                [
                    q["id"],
                    q["question"],
                    first["answer"],
                    second["answer"],
                    q.get("reference_url") or " | ".join(sources),
                ]
                + [""] * 6
            )
    (out / "review-key.json").write_text(
        json.dumps(key, indent=2) + "\n", encoding="utf-8"
    )


def run(args, out):
    corpus, retriever, graph, questions = load_inputs(args.upstream)
    if args.question is not None:
        if not args.question.strip():
            raise ValueError("Question must contain text")
        questions = [
            {
                "id": "custom",
                "kind": "unscored",
                "question": args.question.strip(),
                "expected": [],
            }
        ]
    ids_to_tags = {v: k for k, v in graph["anchors"].items()}
    client = LocalChat(args.base_url, args.model)
    out.mkdir()
    rows = []
    with (out / "answers.jsonl").open("w", encoding="utf-8") as f:
        for i, q in enumerate(questions):
            hits = retriever.search(q["question"], limit=3).hits
            tags = [
                ids_to_tags[h.evidence.id] for h in hits if h.evidence.id in ids_to_tags
            ]
            sources = [
                {
                    "tag": ids_to_tags[h.evidence.id],
                    "id": h.evidence.id,
                    "url": str(corpus.sources[h.evidence.source_id].url),
                    "locator": h.evidence.locator.label,
                }
                for h in hits
                if h.evidence.id in ids_to_tags
            ]
            packets, triples = paired_evidence(graph, tags)
            fingerprint = hashlib.sha256(
                json.dumps(triples, ensure_ascii=False).encode()
            ).hexdigest()
            for condition in ("flat", "graph") if i % 2 == 0 else ("graph", "flat"):
                result = client.generate(q["question"], packets[condition])
                row = {
                    "id": q["id"],
                    "kind": q["kind"],
                    "question": q["question"],
                    "condition": condition,
                    "top_three": [h.evidence.id for h in hits],
                    "annotated_sources": sources,
                    "available_tags": tags,
                    "triples": len(triples),
                    "facts_sha256": fingerprint,
                    **result,
                    **tag_check(result["answer"], tags, q["expected"]),
                }
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
            print(f"{q['id']}: {len(triples)} triples, two replies", flush=True)
    blind_sheet(rows, questions, out)
    eligible = {q["id"] for q in questions if q["expected"]}
    metrics = {}
    for name in ("flat", "graph"):
        group = [r for r in rows if r["condition"] == name]
        metrics[name] = {
            "replies": len(group),
            "expected_citations": sum(r["expected_citation"] for r in group),
            "questions_with_expected_sources": len(eligible),
            "questions_retrieving_expected_source": sum(
                bool(set(r["available_tags"]) & set(q["expected"]))
                for r, q in zip(group, questions, strict=True)
            ),
            "replies_with_invalid_tag": sum(bool(r["out_of_packet"]) for r in group),
            "prompt_tokens_range": [
                min(r["prompt_tokens"] for r in group),
                max(r["prompt_tokens"] for r in group),
            ],
            "output_limit_reached": sum(r["finish_reason"] == "length" for r in group),
        }
    meta = {
        "upstream": UPSTREAM,
        "model_alias": args.model,
        "retrieval_top_k": 3,
        "seed": SEED,
        "temperature": 0,
        "max_output_tokens": TOKEN_LIMIT,
        "max_prompt_tokens": PROMPT_LIMIT,
        "questions": len(questions),
        "anchors": len(graph["anchors"]),
        "nodes": len(graph["nodes"]),
        "relations": len(graph["edges"]),
        "inputs_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [DATA / "persona-graph.json", DATA / "questions.json"]
        },
        "metrics": metrics,
        "human_fidelity_ratings": None,
    }
    if args.question is not None:
        meta["custom_question"] = args.question.strip()
        del meta["inputs_sha256"]["questions.json"]
    (out / "metrics.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18731/v1")
    parser.add_argument("--model", default="qwen2.5-1.5b-instruct-q4_k_m")
    parser.add_argument(
        "--question", help="Optional English question for an unscored paired run"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="A new output directory"
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a new output directory to preserve an earlier run")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        stage = Path(temp) / "result"
        run(args, stage)
        stage.rename(args.out)


if __name__ == "__main__":
    main()
