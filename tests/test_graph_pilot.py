import json
import tempfile
import unittest
from pathlib import Path
from experiment import extract_turns, graph_pilot


class GraphPilotTests(unittest.TestCase):
    def test_same_facts_sources_and_citation_position_in_both_inputs(self):
        graph = graph_pilot.read_json(graph_pilot.DATA / "persona-graph.json")
        packet, triples = graph_pilot.paired_evidence(graph, {"S1", "L1"})
        self.assertEqual(len(triples), 6)
        for tag, subject, relation, obj in triples:
            self.assertIn(f"{subject} {relation} {obj} [{tag}]", packet["flat"])
            self.assertIn(
                f"{relation} → {obj} [{tag}]",
                packet["graph"].split(subject + "\n", 1)[1],
            )
        self.assertNotIn("[A1]", packet["graph"])

    def test_no_evidence_control_gets_identical_input(self):
        data = graph_pilot.read_json(graph_pilot.DATA / "persona-graph.json")
        packets, rows = graph_pilot.paired_evidence(data, [])
        self.assertEqual(packets["flat"], packets["graph"])
        self.assertEqual(rows, [])
        self.assertEqual(
            graph_pilot.tag_check("It was [S1].", [], [])["out_of_packet"], ["S1"]
        )

    def test_tag_metric_cannot_validate_semantics(self):
        metrics = graph_pilot.tag_check(
            "This contradicts the source. [A1]", ["A1"], ["A1"]
        )
        self.assertTrue(metrics["expected_citation"])
        self.assertNotIn("fidelity", metrics)

    def test_caption_settings_and_incomplete_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.vtt"
            path.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:02.050 align:center\nHello\nworld!\n"
            )
            rows = extract_turns.cues(path)
            self.assertEqual(
                extract_turns.select_text(rows, 1000, 2050), "Hello world!"
            )
            with self.assertRaises(ValueError):
                extract_turns.select_text(rows, 1001, 2050)

    def test_archived_pairs_keep_gold_references_out_of_prompt_and_share_facts(self):
        result_dir = graph_pilot.DATA.parent / "results" / "matched-tags"
        questions = graph_pilot.read_json(graph_pilot.DATA / "questions.json")
        rows = [
            json.loads(x)
            for x in (result_dir / "answers.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(rows), len(questions) * 2)
        for question in questions:
            pair = [r for r in rows if r["id"] == question["id"]]
            self.assertEqual({"flat", "graph"}, {r["condition"] for r in pair})
            self.assertEqual(pair[0]["facts_sha256"], pair[1]["facts_sha256"])
            self.assertEqual(pair[0]["available_tags"], pair[1]["available_tags"])
            self.assertNotIn("reference_ko", pair[0])


if __name__ == "__main__":
    unittest.main()
