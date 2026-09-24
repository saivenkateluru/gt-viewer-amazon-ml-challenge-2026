# GT Viewer — Amazon ML Challenge 2026

A local browser viewer for the complete Business Entity Resolution training data.
It connects each Source 1 business to all of its Source 2 and Source 3 ground-truth
matches, including singleton entities.

The challenge data is not stored in this repository. Each user supplies their own
copy when starting the viewer. The files remain local and are ignored by Git.

## Requirements

- Git
- Python 3.9 or newer
- A modern browser
- Several GB of free disk space for the local search index

No Python or JavaScript packages are required.

## 1. Clone

```bash
git clone https://github.com/saivenkateluru/gt-viewer-amazon-ml-challenge-2026.git
cd gt-viewer-amazon-ml-challenge-2026
```

## 2. Supply the training data

Use either method below. Do not commit the challenge data.

### Option A: pass its existing directory

```bash
./run.sh /path/to/student_resource/dataset/train
```

For this challenge workspace, for example:

```bash
./run.sh ../student_resource/dataset/train
```

### Option B: place it in this repository

Create a `data/` directory with this exact structure:

```text
data/
├── train_source1.tsv
├── train_source2.tsv
├── train_source3.tsv
└── train_ground_truth.tsv
```

Then run:

```bash
./run.sh
```

Plain `.tsv` files and gzip-compressed `.tsv.gz` files are both supported.

## 3. Open the viewer

Open <http://127.0.0.1:8000>. Keep the terminal open and press `Ctrl+C` there to
stop the server.

The first run builds `.cache/viewer.sqlite3`. This one-time indexing step can take
several minutes because it processes every training record. Later runs reuse the
index and start immediately. The index rebuilds automatically if any input file
changes.

To build the index without starting the server:

```bash
python3 server.py --data-dir /path/to/dataset/train --build-only
```

To use another port:

```bash
./run.sh /path/to/dataset/train 8001
```

Then open <http://127.0.0.1:8001>.

### Windows PowerShell

```powershell
python server.py --data-dir "C:\path\to\student_resource\dataset\train"
```

## Using the viewer

1. Search for a Source 1 entity ID, business name, or address.
2. Filter by country or relationship count.
3. Select a Source 1 result to display its complete ground-truth graph.
4. Select an orange Source 2 or green Source 3 node to compare raw fields with
   the blue Source 1 reference record.
5. Select **Singletons** under Relationships to inspect entities without matches.

Search returns the first 40 results to keep the interface and API responsive. Refine
the query to find a particular entity; the underlying index contains every row.

## Performance design

- SQLite and FTS5 provide indexed local search without loading the dataset into
  browser memory.
- The index builder uses a bounded 128 MB SQLite cache and disk-backed temporary
  storage.
- Runtime queries use a 16 MB SQLite cache and return at most 40 Source 1 groups.
- Search waits 250 ms after typing and cancels stale requests.
- Only the selected result page and its ground-truth neighbors cross the local API.
- Exact full-result counts are intentionally skipped because counting millions of
  filtered records adds latency without improving exploration.

## Troubleshooting

- **Training data not found:** verify the directory contains all four required
  files with the exact names shown above.
- **`Permission denied` for `run.sh`:** run `chmod +x run.sh`, or invoke
  `python3 server.py --data-dir /path/to/train`.
- **Port 8000 is busy:** pass another port as the second argument.
- **Force an index rebuild:** stop the server and delete `.cache/viewer.sqlite3`.
- **Remote machine:** use SSH port forwarding. Bind to `0.0.0.0` only on a trusted
  network with appropriate firewall controls.

## Data policy

The viewer performs no external business lookup, address lookup, geocoding, or data
enrichment. The challenge files and generated index remain on the user's machine.
The MIT license covers the viewer code, not the challenge dataset.
