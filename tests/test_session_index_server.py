import gzip
from contextlib import closing, contextmanager
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("index_server", Path(__file__).parents[1] / "tools/session-index-server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@contextmanager
def open_db(path):
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


class IndexServerTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="yanhe-index-unit-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        server.database(self.root).parent.mkdir()
        with open_db(server.database(self.root)) as db:
            db.executescript("""
                CREATE TABLE courses(id INTEGER PRIMARY KEY,name_zh TEXT,number TEXT,
                    school_year TEXT,semester INTEGER,professors TEXT,professor_names TEXT,extra TEXT);
                CREATE TABLE sessions(id INTEGER PRIMARY KEY,course_id INTEGER,gone_at INTEGER);
                CREATE TABLE crawl_state(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE failures(kind TEXT,id INTEGER);
                CREATE TABLE gaps(from_id INTEGER,to_id INTEGER);
                CREATE TABLE runs(requests INTEGER);
                INSERT INTO courses VALUES(9397,'离散数学Ⅱ',NULL,'2020-2021',2,
                    '[{"name":"教师甲","badge":"private-staff-number"}]',NULL,'credential-example');
                INSERT INTO courses VALUES(71990,'材料电化学',NULL,'2026-2027',1,'null','教师乙',NULL);
                INSERT INTO sessions VALUES(71990,9397,NULL),(72000,9397,NULL),(72001,9397,1);
                INSERT INTO runs VALUES(2);
            """)

    def test_plain_data_retains_course_session_identity_and_excludes_removed_sessions(self):
        result = server.export(self.root)
        data = json.loads((self.root / "exports/catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(data["courses"][0]["id"], 9397)
        self.assertEqual(data["courses"][0]["sessions"], [71990, 72000])
        self.assertEqual(data["courses"][1]["id"], 71990)
        self.assertEqual(data["courses"][1]["sessions"], [])
        self.assertEqual(result["sessions"], 2)
        self.assertEqual(data["courses"][0]["term"], "2020-2021-2")
        self.assertTrue(data["partial"])

    def test_export_contains_teacher_names_without_staff_ids_or_unselected_extra_fields(self):
        server.export(self.root)
        raw = (self.root / "exports/catalog.json").read_text(encoding="utf-8")
        self.assertNotIn("private-staff-number", raw)
        self.assertNotIn("credential-example", raw)
        self.assertEqual(json.loads(raw)["courses"][1]["teachers"], ["教师乙"])

    def test_plain_and_compressed_exports_are_identical_and_status_hash_matches(self):
        server.export(self.root)
        raw = (self.root / "exports/catalog.json").read_bytes()
        self.assertEqual(gzip.decompress((self.root / "exports/catalog.json.gz").read_bytes()), raw)
        report = json.loads((self.root / "exports/status.json").read_text())
        self.assertEqual(report["catalogSha256"], server.hashlib.sha256(raw).hexdigest())

    def test_unknown_terms_and_null_teacher_lists_are_kept(self):
        with open_db(server.database(self.root)) as db:
            db.execute("UPDATE courses SET school_year=NULL,professors='null',professor_names=NULL WHERE id=9397")
        server.export(self.root)
        row = json.loads((self.root / "exports/catalog.json").read_text(encoding="utf-8"))["courses"][0]
        self.assertEqual(row["sessions"], [71990, 72000])
        self.assertIsNone(row["term"])
        self.assertEqual(row["teachers"], [])

    def test_progress_resumes_from_upstream_lane_cursor(self):
        with open_db(server.database(self.root)) as db:
            db.execute("INSERT INTO crawl_state VALUES(?,?)", (
                "lane:range:932000:1000000", json.dumps({"cursor": 932025, "done": False})))
        report = server.status(self.root)
        self.assertEqual(report["ranges"][0]["next"], 932025)
        self.assertEqual(report["progressIds"], 25)
        self.assertEqual(report["scopeIds"], 1000000)

    def test_old_lane_is_split_without_changing_total_progress_or_old_cursor(self):
        previous = {"cursor": 907901, "missRun": 2, "missRunStart": 907903,
                    "parkedUntilMs": None, "done": False}
        with open_db(server.database(self.root)) as db:
            db.execute("INSERT INTO crawl_state VALUES(?,?)", (server.LEGACY_HISTORY_KEY, json.dumps(previous)))
        before = server.status(self.root)
        self.assertEqual(before["progressIds"], 931999 - 907901)
        self.assertEqual(before["scopeIds"], 1000000)
        self.assertEqual(before["ranges"][1]["next"], 907901)
        self.assertEqual(before["ranges"][2]["next"], 892999)
        self.assertEqual(server.active_schedule(before), [2])
        self.assertEqual(len(server.migrate_lanes(self.root)), 2)
        self.assertEqual(server.status(self.root), before)
        self.assertEqual(server.migrate_lanes(self.root), [], "migration is idempotent")
        with open_db(server.database(self.root)) as db:
            self.assertEqual(json.loads(db.execute("SELECT value FROM crawl_state WHERE key=?", (server.LEGACY_HISTORY_KEY,)).fetchone()[0]), previous)

    def test_split_reuses_progress_already_below_the_estimated_boundary(self):
        with open_db(server.database(self.root)) as db:
            db.execute("INSERT INTO crawl_state VALUES(?,?)", (server.LEGACY_HISTORY_KEY, json.dumps({"cursor": 823123, "done": False})))
        result = server.status(self.root)
        self.assertTrue(result["ranges"][1]["done"])
        self.assertEqual(result["ranges"][2]["next"], 823123)
        self.assertEqual(result["progressIds"], 931999 - 823123)
        self.assertEqual(result["scopeIds"], 1000000)

    def test_migration_never_overwrites_new_historical_progress(self):
        with open_db(server.database(self.root)) as db:
            db.execute("INSERT INTO crawl_state VALUES(?,?)", (server.LEGACY_HISTORY_KEY, json.dumps({"cursor": 907901, "done": False})))
            db.execute("INSERT INTO crawl_state VALUES(?,?)", ("lane:range:892999:1", json.dumps({"cursor": 800000, "done": False})))
        server.migrate_lanes(self.root)
        self.assertEqual(server.status(self.root)["ranges"][2]["next"], 800000)

    def test_finish_historical_priority_then_visit_all_remaining_ids(self):
        with open_db(server.database(self.root)) as db:
            db.execute("INSERT INTO crawl_state VALUES(?,?)", ("lane:range:892999:1", json.dumps({"cursor": 0, "done": True})))
        result = server.status(self.root)
        self.assertTrue(result["historicalPriorityDone"])
        self.assertEqual(server.active_schedule(result), [1, 0])
        self.assertFalse(result["complete"], "deferred current-term ids are still unscanned")

    def test_approximate_boundary_does_not_relabel_or_drop_current_term_courses(self):
        server.export(self.root)
        data = json.loads((self.root / "exports/catalog.json").read_text(encoding="utf-8"))
        self.assertTrue(data["collectionPolicy"]["estimated"])
        self.assertEqual(data["collectionPolicy"]["historyBoundaryHint"], 893000)
        self.assertEqual(data["courses"][1]["term"], "2026-2027-1")

    def test_unresolved_errors_prevent_a_complete_label(self):
        with open_db(server.database(self.root)) as db:
            for start, end in server.RANGES:
                db.execute("INSERT INTO crawl_state VALUES(?,?)", (
                    f"lane:range:{start}:{end}", json.dumps({"cursor": end, "done": True})))
            db.execute("INSERT INTO failures VALUES('session',888888)")
        self.assertFalse(server.status(self.root)["complete"])
        with open_db(server.database(self.root)) as db:
            db.execute("DELETE FROM failures")
        self.assertTrue(server.status(self.root)["complete"])

    def test_failed_atomic_replace_preserves_previous_file(self):
        target = self.root / "existing.json"
        target.write_bytes(b"old data")
        with patch.object(server.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                server.atomic_bytes(target, b"new data")
        self.assertEqual(target.read_bytes(), b"old data")
        self.assertEqual(list(self.root.glob(".index-*")), [])

    def test_collector_command_has_no_gap_skipping_media_download_or_upload(self):
        command = server.collector_command(self.root, 932000, 1000000, 300)
        self.assertEqual(command[command.index("--interval-ms") + 1], "200")
        self.assertEqual(command[command.index("--concurrency") + 1], "5")
        self.assertGreaterEqual(int(command[command.index("--gap-threshold") + 1]), 1000000)
        for flag in ["--videos", "--only-videos", "--upload", "--env-file-if-exists"]:
            self.assertNotIn(flag, command)
        with patch.dict(os.environ, {"CF_API_TOKEN": "private", "INDEX_CLIENT_PASSPHRASE": "private", "GITHUB_TOKEN": "private"}):
            self.assertFalse(any(k.startswith(("CF_", "INDEX_", "GITHUB_")) for k in server.environment()))


if __name__ == "__main__":
    unittest.main()
