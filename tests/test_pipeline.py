import json
import tempfile
import unittest
from pathlib import Path

from build_cards import DATA, build_cards, load_sources, searchable, studio_record
from search_cards import search


class EvidencePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = build_cards(DATA / "turns.jsonl", DATA / "sources.json")

    def test_search_returns_original_exchange_and_source(self):
        hit, = search(self.cards, "엔비디아에서 미션은 무슨 뜻인가요?", 1)
        self.assertEqual(hit["evidence_id"], "ACQ-04")
        self.assertEqual(hit["exchange"]["answer"], "Build Hopper.")
        self.assertIn("acquired.fm", hit["source_url"])
        self.assertEqual(hit["text_provenance"], "editorial_summary")

    def test_holdout_and_draft_documents_are_unsearchable(self):
        clean = self.cards[0]
        for change in ({"source_split": "test"}, {"source_split": "validation"}, {"review_status": "draft"}):
            with self.subTest(change=change):
                ineligible = dict(clean, **change)
                self.assertFalse(searchable(ineligible))
                self.assertEqual(search([ineligible], "창업", 1), [])

    def test_event_cannot_span_multiple_splits(self):
        source = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))[0]
        variant = dict(source, id="other-transcript", split="test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps([source, variant]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inconsistent split"):
                load_sources(path)

    def test_text_export_and_timestamp_provenance(self):
        hit, = search(self.cards, "공감 관대함", 1)
        record = studio_record(hit)
        self.assertEqual(hit["evidence_id"], "LEX-01")
        self.assertEqual(record["locator"]["start_seconds"], 8155)
        self.assertNotIn("end_seconds", record["locator"])
        self.assertEqual(record["projection_eligibility"],
                         {"factual": True, "text_style": False, "aligned_speech": False, "visible_behavior": False})


if __name__ == "__main__":
    unittest.main()
