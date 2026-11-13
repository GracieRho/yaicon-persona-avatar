import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import stage_rehearsal
from stage_qa import PILOT, StageQA, draft_messages, model_draft, read_json


class StageQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = StageQA()

    def test_korean_rehearsal_routes_sources_and_application(self):
        cases = read_json(PILOT / "stage-questions.json")
        report = stage_rehearsal.run(cases, self.qa)
        for row in report["rows"]:
            with self.subTest(row["id"]):
                self.assertTrue(row["matches"])
        self.assertEqual(len({q["id"] for q in cases}), len(cases))
        self.assertIsNone(report["human_persona_fidelity"])

    def test_graph_paths_are_bounded_to_the_selected_evidence(self):
        for tag in self.qa.graph["anchors"]:
            triples = self.qa.relations(tag)
            nodes = self.qa.graph["nodes"]
            allowed = [(nodes[a], rel, nodes[b]) for t, a, rel, b in self.qa.graph["edges"] if t == tag]
            self.assertTrue(triples)
            self.assertTrue(set(triples) <= set(allowed))
        work = self.qa.relations("S1")
        self.assertEqual(work[0][2], work[1][0])
        self.assertEqual(len(self.qa.relations("L1")), 2)
        self.assertEqual(self.qa.persona["H1"]["url"], "https://lexfridman.com/jensen-huang-transcript/")

    def test_mixed_answer_keeps_team_and_attribution_distinct(self):
        result = self.qa.answer("시선 추적을 어떻게 구현했나요? 젠슨 황 관점에서 어떤 테스트를 해야 할까요?")
        self.assertEqual([s["kind"] for s in result["sections"]],
                         ["team_fact", "persona_evidence", "application"])
        self.assertEqual(result["sections"][-1]["basis"], "A1")
        self.assertNotIn("http", result["spoken_text"])
        self.assertEqual(result["rendering"], "authored")

    def test_followup_cannot_borrow_evidence_for_a_new_unknown_claim(self):
        previous = "Qwen의 한국어 응답 시간을 측정한 결과는요?"
        self.assertEqual(self.qa.answer("그럼 표본수는요?", previous)["sources"], [])
        self.assertEqual(self.qa.answer("그럼 비공개 회의에서는 뭐라고 했나요?", previous)["sources"], [])
        self.assertEqual(self.qa.answer("RAG의 정의는요?", previous)["route"], "technical_fact")

    def test_local_slide_pack_can_add_a_fact_missing_from_public_docs(self):
        q = "이번 발표의 예산은 얼마인가요?"
        self.assertEqual(self.qa.answer(q)["route"], "insufficient")
        slide = {"P-slide-test": {"kind": "project", "url": "https://example.org/rehearsal",
                                 "locator": "리허설용 가상 슬라이드", "text": "테스트용 예산은 5원입니다.",
                                 "terms": ["예산"]}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "slides.json"
            path.write_text(json.dumps(slide), encoding="utf-8")
            self.assertEqual(StageQA(path).answer(q)["sources"][0]["id"], "P-slide-test")
            slide["P-gaze"] = slide.pop("P-slide-test")
            path.write_text(json.dumps(slide), encoding="utf-8")
            with self.assertRaises(ValueError):
                StageQA(path)

    def test_drafts_share_evidence_and_exclude_authored_advice(self):
        packet = self.qa.answer("테스트 없이 출시해도 될까요?")
        graph, flat = [json.loads(draft_messages(packet, mode)[1]["content"]) for mode in ("graph", "flat")]
        row = graph["sections"][0]
        triples = row.pop("evidence")
        self.assertEqual(flat["sections"][0].pop("evidence"), [f"{a} {r} {b}." for a, r, b in triples])
        self.assertEqual(graph, flat)
        self.assertNotIn(packet["sections"][-1]["answer"], json.dumps(graph, ensure_ascii=False))

    def test_unknown_evidence_skips_generation(self):
        with patch("stage_qa.urlopen") as service:
            self.assertIsNone(model_draft(self.qa.answer("내일 주가가 얼마일까요?"), "unused", "unused"))
            service.assert_not_called()
