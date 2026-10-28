import tempfile
import threading
import unittest
from pathlib import Path

from loglens.reader import MAX_LINE, Filters, Tail, level_of, search


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / "service.log"
        self.path.write_text(
            'INFO Started\nERROR Network\n{"level":"warning","message":"Disk"}\n', encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_search_and_level_filter(self):
        result = search(self.path, "network", "ERROR")
        self.assertEqual(result["rows"], [(2, "ERROR", "ERROR Network")])
        self.assertEqual(search(self.path, "network", case_sensitive=True)["rows"], [])

    def test_json_levels_and_unstructured_lines(self):
        self.assertEqual(level_of('{"level":"warning"}'), "WARN")
        self.assertEqual(level_of("no severity"), "—")
        self.assertEqual(level_of("{invalid json"), "—")

    def test_results_are_bounded(self):
        result = search(self.path, limit=1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertTrue(result["limited"])

    def test_long_lines_are_skipped_without_losing_line_numbers(self):
        self.path.write_bytes(b"x" * (MAX_LINE + 20) + b"\nERROR end\n")
        result = search(self.path)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["rows"][0][0], 2)

    def test_cancellation_does_not_scan_the_entire_file(self):
        stop = threading.Event()
        stop.set()
        result = search(self.path, cancel=stop)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["scanned"], 0)

    def test_tail_waits_for_complete_lines(self):
        tail = Tail(self.path)
        with self.path.open("ab") as file:
            file.write(b"partial")
        self.assertEqual(tail.read()[1], [])
        with self.path.open("ab") as file:
            file.write(b" line\n")
        self.assertEqual(tail.read()[1], ["partial line"])

    def test_tail_detects_truncation(self):
        tail = Tail(self.path)
        self.path.write_bytes(b"INFO new\n")
        reset, lines = tail.read()
        self.assertTrue(reset)
        self.assertEqual(lines, ["INFO new"])

    def test_saved_filters_are_persistent(self):
        filters = Filters(self.root / "filters.json")
        filters.save("Errors", "network", "ERROR", False)
        self.assertEqual(Filters(filters.path).all()["Errors"]["query"], "network")

    def test_invalid_utf8_is_readable(self):
        self.path.write_bytes(b"INFO \xff\n")
        self.assertIn("\ufffd", search(self.path)["rows"][0][2])
