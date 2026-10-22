import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/aistylebook-48/scripts/stylebook.py"
spec = importlib.util.spec_from_file_location("stylebook", SCRIPT)
stylebook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stylebook)


class StylebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = stylebook.load_catalog()

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")

    def test_exactly_48_complete_cards(self):
        self.assertEqual([row["id"] for row in self.catalog], list(range(1, 49)))
        self.assertEqual(len({row["slug"] for row in self.catalog}), 48)
        for row in self.catalog:
            with self.subTest(id=row["id"]):
                card = stylebook.card_for(row)
                self.assertEqual(card["name"], row["name"])
                self.assertEqual(len(card["signature"]), 3)
                self.assertTrue(len(card["rendering_prompt"]) > 100)
                self.assertTrue(all(1 <= value <= 48 and value != row["id"] for value in card["nearby_styles"]))

    def test_every_name_id_slug_resolves(self):
        for row in self.catalog:
            for query in (str(row["id"]), f"{row['id']:02d}", row["name"], row["name_en"], row["slug"]):
                with self.subTest(query=query):
                    self.assertEqual(stylebook.resolve(query, self.catalog)["id"], row["id"])

    def test_search_exact_and_visual_features(self):
        self.assertEqual(stylebook.search("watercolor", self.catalog)[0]["id"], 45)
        self.assertEqual(stylebook.search("毛毡", self.catalog)[0]["id"], 26)
        self.assertIn(13, [row["id"] for row in stylebook.search("纸张 手工", self.catalog, 3)])
        self.assertEqual(stylebook.search("thisisinvented", self.catalog), [])
        self.assertEqual(stylebook.search("", self.catalog), [])
        self.assertNotIn(21, [row["id"] for row in stylebook.search("documentary", self.catalog)])

    def test_out_of_range_never_selects_another_style(self):
        for query in ("0", "49", "1001", "#99"):
            self.assertEqual(stylebook.search(query, self.catalog), [])
            with self.assertRaises(ValueError):
                stylebook.resolve(query, self.catalog)
        result = self.run_cli("show", "99")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://aistylebook.com/", result.stderr)

    def test_search_can_run_from_another_directory(self):
        result = self.run_cli("show", "水彩", "--json", cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["id"], 45)

    def test_prompt_keeps_user_content_and_selected_medium(self):
        result = self.run_cli("prompt", "26", "--subject", "a blue teapot", "--subject-type", "objects", "--mode", "transfer", "--ratio", "4:3", "--preserve", "handle and spout")
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("a blue teapot", "handle and spout", "4:3", "needle-felted", "reference image", "functional structure"):
            self.assertIn(expected, result.stdout)

    def test_all_styles_make_distinct_prompts(self):
        prompts = set()
        for row in self.catalog:
            prompt = stylebook.make_prompt(row, stylebook.card_for(row), "a red bicycle", "objects")
            self.assertIn("a red bicycle", prompt)
            prompts.add(prompt)
        self.assertEqual(len(prompts), 48)

    def test_invalid_ratio_empty_subject_and_invalid_limit(self):
        for args in (("prompt", "45", "--subject", "bike", "--ratio", "0:3"), ("prompt", "45", "--subject", " "), ("search", "paper", "--limit", "0")):
            self.assertNotEqual(self.run_cli(*args).returncode, 0)

    def test_json_empty_search_has_failure_exit_code(self):
        result = self.run_cli("search", "unknownstylexyz", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
