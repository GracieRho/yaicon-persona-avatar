import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiment.persona_v2 import PersonaGraph, paired_context, route, validate_answer, run, DATA
from experiment.aligned_manifest import build


class PersonaV2Tests(unittest.TestCase):
    def setUp(self):
        self.graph = PersonaGraph()

    def test_mixed_news_does_not_retrieve_persona(self):
        for q in ("이번 불륜 이슈에 대해 리더라면 어떤 위험을 고려해야 할까요?",
                  "사원들의 복귀 찬성 여론이 있다는데 회의와 시간배분을 어떻게 바꾸실 건가요?",
                  "일론 머스크가 진짜 섭외 요청을 했나요? 회의에서 무슨 얘기를 나누셨어요?"):
            self.assertNotEqual(self.graph.packet(q)["decision"], "persona")
            self.assertEqual(self.graph.packet(q)["sources"], {})

    def test_eligibility_never_reintroduces_filtered_source(self):
        self.assertEqual(self.graph.packet("testing before a risk", allowed_evidence_ids=[])["sources"], {})
        a = self.graph.anchors["A1"]["evidence_id"]
        self.assertEqual(set(self.graph.packet("testing before a risk", [a])["sources"]), {"A1"})

    def test_serializations_preserve_identical_typed_relations(self):
        packet = self.graph.packet("testing before a risk")
        contexts, _ = paired_context(packet)
        restored = [{"head": h, **e} for h, edges in contexts["graph"]["adjacency"].items() for e in edges]
        key = lambda e: json.dumps(e, sort_keys=True)
        self.assertEqual(sorted(restored, key=key), sorted(contexts["flat"]["relations"], key=key))
        self.assertEqual(contexts["flat"]["sources"], contexts["graph"]["sources"])
        self.assertIn("rejected", contexts["graph"]["sources"]["A1"]["summary_en"])

    def test_invalid_and_empty_evidence_citations_rejected(self):
        p = self.graph.packet("exact hourly wage")
        self.assertTrue(validate_answer({"answer": "Made up", "citations": ["S1"], "application": True}, p))
        self.assertEqual(validate_answer({"answer": "There is no supporting evidence.", "citations": [], "application": False}, p), [])

    def test_schema_catches_nonboolean_application(self):
        p = self.graph.packet("testing")
        self.assertIn("invalid_application_flag", validate_answer({"answer":"a","citations":[],"application":"false"}, p))

    def test_missing_media_never_promoted(self):
        m = build()
        self.assertEqual(m["training_eligible_count"], 0)
        self.assertEqual(m["assets_available_count"], 0)
        self.assertTrue(all(not t["review"]["acoustic_alignment_verified"] for t in m["turns"]))

    def test_forged_review_without_assets_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"review.json"; p.write_text(json.dumps({"stripe24-effort":{"speaker_verified":True}}))
            with self.assertRaises(ValueError): build(review=p)

    def test_graph_rejects_unanchored_relation(self):
        d = json.loads((DATA/"graph.json").read_text()); d["edges"][0]["source"]="FAKE"
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"g.json";p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):PersonaGraph(p)

    def test_preparation_does_not_invent_generations(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/"run"
            with patch("experiment.persona_v2.generate", side_effect=AssertionError("No endpoint")):
                summary=run(out)
            self.assertEqual(summary["generation_requests"],0)
            self.assertIsNone(summary["semantic_fidelity"])
            self.assertFalse((out/"answers.jsonl").exists())
            self.assertFalse(summary["promote_to_team"])
            prompts=json.loads((out/"prompts.json").read_text())
            self.assertNotIn("expected_sources",json.dumps(prompts))
            self.assertNotIn("rubric",json.dumps(prompts))


if __name__ == "__main__":
    unittest.main()
