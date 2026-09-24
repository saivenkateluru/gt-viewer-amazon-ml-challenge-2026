#!/usr/bin/env python3
"""Index the complete challenge training data and serve the local viewer."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import http.server
import json
import os
import re
import sqlite3
import urllib.parse
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
REQUIRED_FILES = (
    "train_source1.tsv",
    "train_source2.tsv",
    "train_source3.tsv",
    "train_ground_truth.tsv",
)


def resolve_files(data_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    missing: list[str] = []
    for name in REQUIRED_FILES:
        plain = data_dir / name
        compressed = data_dir / f"{name}.gz"
        if plain.is_file():
            files[name] = plain
        elif compressed.is_file():
            files[name] = compressed
        else:
            missing.append(name)
    if missing:
        names = "\n  - ".join(missing)
        raise SystemExit(
            f"Training data not found in {data_dir}\n"
            f"Missing:\n  - {names}\n\n"
            "Run: ./run.sh /path/to/student_resource/dataset/train"
        )
    return files


def open_text(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    return opener(path, "rt", encoding="utf-8", errors="replace", newline="")


def data_signature(files: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(files.items()):
        stat = path.stat()
        digest.update(f"{name}:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def insert_records(connection: sqlite3.Connection, path: Path, source: str) -> tuple[int, dict[str, int]]:
    count = 0
    countries: dict[str, int] = {}
    batch: list[tuple[str, str, str, str, str]] = []
    with open_text(path) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            country = row["country"] or "Unknown"
            batch.append((row["entity_id"], source, row["business_name"], row["business_address"], country))
            count += 1
            if source == "S1":
                countries[country] = countries.get(country, 0) + 1
            if len(batch) >= 25_000:
                connection.executemany("INSERT INTO records VALUES (?,?,?,?,?)", batch)
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO records VALUES (?,?,?,?,?)", batch)
    connection.commit()
    return count, countries


def insert_ground_truth(connection: sqlite3.Connection, path: Path) -> tuple[int, int]:
    count = 0
    singletons = 0
    batch: list[tuple[str, str, int]] = []
    with open_text(path) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            matched = row["matched_entity_ids"]
            match_count = 0 if not matched else matched.count(",") + 1
            singletons += match_count == 0
            count += 1
            batch.append((row["source1_entity_id"], matched, match_count))
            if len(batch) >= 25_000:
                connection.executemany("INSERT INTO ground_truth VALUES (?,?,?)", batch)
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO ground_truth VALUES (?,?,?)", batch)
    connection.commit()
    return count, singletons


def build_database(database: Path, files: dict[str, Path], signature: str) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    print("Building the local search index. This one-time step can take several minutes.", flush=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=FILE;
            PRAGMA cache_size=-131072;
            PRAGMA page_size=8192;
            CREATE TABLE records (
                entity_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                business_name TEXT NOT NULL,
                business_address TEXT NOT NULL,
                country TEXT NOT NULL
            );
            CREATE TABLE ground_truth (
                source1_entity_id TEXT PRIMARY KEY,
                matched_entity_ids TEXT NOT NULL,
                match_count INTEGER NOT NULL
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        total_records = 0
        countries: dict[str, int] = {}
        for source, filename in (("S1", "train_source1.tsv"), ("S2", "train_source2.tsv"), ("S3", "train_source3.tsv")):
            print(f"Indexing {filename}…", flush=True)
            count, source_countries = insert_records(connection, files[filename], source)
            total_records += count
            countries.update(source_countries)

        print("Indexing train_ground_truth.tsv…", flush=True)
        group_count, singleton_count = insert_ground_truth(connection, files["train_ground_truth.tsv"])
        connection.executescript("""
            CREATE INDEX records_source_country ON records(source, country);
            CREATE INDEX ground_truth_match_count ON ground_truth(match_count);
            CREATE VIRTUAL TABLE s1_search USING fts5(entity_id, business_name, business_address);
            INSERT INTO s1_search(rowid, entity_id, business_name, business_address)
                SELECT rowid, entity_id, business_name, business_address FROM records WHERE source='S1';
        """)
        stats = {
            "description": "Complete Amazon ML Challenge 2026 training ground truth",
            "groupCount": group_count,
            "recordCount": total_records,
            "singletonCount": singleton_count,
            "countries": countries,
        }
        connection.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            (("signature", signature), ("stats", json.dumps(stats, ensure_ascii=False))),
        )
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, database)
    print(f"Index ready: {database}", flush=True)


def ensure_database(database: Path, files: dict[str, Path]) -> None:
    signature = data_signature(files)
    if database.is_file():
        try:
            with sqlite3.connect(database) as connection:
                stored = connection.execute("SELECT value FROM metadata WHERE key='signature'").fetchone()
            if stored and stored[0] == signature:
                return
        except sqlite3.Error:
            pass
    build_database(database, files, signature)


def record(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["entity_id"],
        "name": row["business_name"],
        "address": row["business_address"],
        "country": row["country"],
        "source": row["source"],
    }


def fts_query(value: str) -> str:
    tokens = re.findall(r"\w+", value, flags=re.UNICODE)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens[:12])


def open_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA cache_size=-16384")
    connection.execute("PRAGMA mmap_size=67108864")
    return connection


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    database: Path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_ROOT, **kwargs)

    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def groups(self, query: dict[str, list[str]]) -> dict[str, object]:
        search = query.get("q", [""])[0].strip()
        country = query.get("country", ["all"])[0]
        match_filter = query.get("match", ["all"])[0]
        sort = query.get("sort", ["default"])[0]
        limit = min(max(int(query.get("limit", ["40"])[0]), 1), 100)

        conditions: list[str] = []
        parameters: list[object] = []
        match_expression = fts_query(search)
        if search and match_expression:
            source = (
                "FROM s1_search CROSS JOIN records r ON r.rowid=s1_search.rowid "
                "CROSS JOIN ground_truth g ON g.source1_entity_id=r.entity_id"
            )
            conditions.append("s1_search MATCH ?")
            parameters.append(match_expression)
            default_ordering = "ORDER BY bm25(s1_search)"
        else:
            source = "FROM ground_truth g CROSS JOIN records r ON r.entity_id=g.source1_entity_id"
            default_ordering = "ORDER BY g.rowid"
        ordering = {
            "matches_desc": "ORDER BY g.match_count DESC",
            "matches_asc": "ORDER BY g.match_count ASC",
        }.get(sort, default_ordering)
        if country != "all":
            conditions.append("r.country=?")
            parameters.append(country)
        match_conditions = {
            "matched": "COALESCE(g.match_count,0)>0",
            "singleton": "COALESCE(g.match_count,0)=0",
            "1-2": "COALESCE(g.match_count,0) BETWEEN 1 AND 2",
            "3-5": "COALESCE(g.match_count,0) BETWEEN 3 AND 5",
            "6+": "COALESCE(g.match_count,0)>=6",
        }
        if match_filter in match_conditions:
            conditions.append(match_conditions[match_filter])

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        base = f"{source}{where}"
        with closing(open_database(self.database)) as connection:
            rows = connection.execute(
                f"SELECT r.*,g.matched_entity_ids,g.match_count {base} {ordering} LIMIT ?",
                [*parameters, limit + 1],
            ).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            match_ids = [
                entity_id
                for row in rows
                for entity_id in (row["matched_entity_ids"] or "").split(",")
                if entity_id
            ]
            matches: dict[str, dict[str, str]] = {}
            for start in range(0, len(match_ids), 500):
                chunk = match_ids[start:start + 500]
                placeholders = ",".join("?" for _ in chunk)
                for match in connection.execute(f"SELECT * FROM records WHERE entity_id IN ({placeholders})", chunk):
                    matches[match["entity_id"]] = record(match)

        groups = []
        for row in rows:
            ids = [value for value in (row["matched_entity_ids"] or "").split(",") if value]
            groups.append({"source1": record(row), "matches": [matches[value] for value in ids if value in matches]})
        return {"groups": groups, "hasMore": has_more, "limit": limit}

    def entity(self, entity_id: str) -> dict[str, object] | None:
        with closing(open_database(self.database)) as connection:
            row = connection.execute(
                "SELECT r.*,g.matched_entity_ids FROM records r LEFT JOIN ground_truth g "
                "ON g.source1_entity_id=r.entity_id WHERE r.entity_id=? AND r.source='S1'",
                (entity_id,),
            ).fetchone()
            if not row:
                return None
            ids = [value for value in (row["matched_entity_ids"] or "").split(",") if value]
            found: dict[str, dict[str, str]] = {}
            if ids:
                placeholders = ",".join("?" for _ in ids)
                for match in connection.execute(f"SELECT * FROM records WHERE entity_id IN ({placeholders})", ids):
                    found[match["entity_id"]] = record(match)
        return {"source1": record(row), "matches": [found[value] for value in ids if value in found]}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/stats":
                with closing(open_database(self.database)) as connection:
                    stats = connection.execute("SELECT value FROM metadata WHERE key='stats'").fetchone()[0]
                self.send_json(json.loads(stats))
                return
            if parsed.path == "/api/entities":
                self.send_json(self.groups(urllib.parse.parse_qs(parsed.query)))
                return
            if parsed.path.startswith("/api/entity/"):
                payload = self.entity(urllib.parse.unquote(parsed.path.removeprefix("/api/entity/")))
                self.send_json(payload or {"error": "Entity not found"}, 200 if payload else 404)
                return
        except (ValueError, sqlite3.Error) as error:
            self.send_json({"error": str(error)}, 400)
            return
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--database", type=Path, default=ROOT / ".cache" / "viewer.sqlite3")
    parser.add_argument("--build-only", action="store_true", help="build the index, then exit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    data_dir = args.data_dir.expanduser().resolve()
    files = resolve_files(data_dir)
    ensure_database(args.database, files)
    if args.build_only:
        return
    ViewerHandler.database = args.database

    server = http.server.ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    try:
        print(f"GT Viewer: http://{args.host}:{args.port}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
