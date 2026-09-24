import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import server


class IndexTest(unittest.TestCase):
    def test_builds_searchable_ground_truth_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
            (root / "train_source1.tsv").write_text(header + "S1-1\tAlpha Shop\tOne Road\tUS\n", encoding="utf-8")
            (root / "train_source2.tsv").write_text(header + "S2-1\tAlpha Store\t1 Rd\tUS\n", encoding="utf-8")
            (root / "train_source3.tsv").write_text(header + "S3-1\tBeta\tTwo Road\tUS\n", encoding="utf-8")
            (root / "train_ground_truth.tsv").write_text(
                "source1_entity_id\tmatched_entity_ids\nS1-1\tS2-1\n", encoding="utf-8"
            )
            files = server.resolve_files(root)
            database = root / "viewer.sqlite3"
            server.build_database(database, files, server.data_signature(files))

            with sqlite3.connect(database) as connection:
                stats = json.loads(connection.execute("SELECT value FROM metadata WHERE key='stats'").fetchone()[0])
                found = connection.execute(
                    "SELECT entity_id FROM s1_search WHERE s1_search MATCH ?", (server.fts_query("Alpha"),)
                ).fetchone()[0]

            self.assertEqual(stats["recordCount"], 3)
            self.assertEqual(stats["groupCount"], 1)
            self.assertEqual(found, "S1-1")


if __name__ == "__main__":
    unittest.main()
