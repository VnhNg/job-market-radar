import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "data" / "raw" / "adzuna" / "de" / "jobs_search"


def request_path_from_response(response_path: Path) -> Path:
    return response_path.with_name(
        response_path.name.replace("response_", "request_").replace(".json", "_params.json")
    )


def parse_pair(response_path: Path) -> Optional[dict]:
    req_path = request_path_from_response(response_path)
    try:
        req = json.loads(req_path.read_text(encoding="utf-8"))
        res = json.loads(response_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    params = req.get("params") or {}
    results = res.get("results") or []
    return {
        "download_date": response_path.parent.name,
        "timestamp_local": req.get("timestamp_local"),
        "url": req.get("url"),
        "what": params.get("what"),
        "where": params.get("where"),
        "results_per_page": params.get("results_per_page"),
        "sort_by": params.get("sort_by"),
        "what_exclude": params.get("what_exclude"),
        "count": res.get("count"),
        "n_results": len(results) if isinstance(results, list) else 0,
        "request_file": str(req_path.relative_to(PROJECT_ROOT).as_posix()),
        "response_file": str(response_path.relative_to(PROJECT_ROOT).as_posix()),
    }


def main() -> int:
    response_files = sorted(BASE.glob("*/*response_*.json"))
    if not response_files:
        print(f"No response files found under: {BASE}")
        return 0

    rows = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(parse_pair, fp) for fp in response_files]
        for fut in as_completed(futures):
            row = fut.result()
            if row is not None:
                rows.append(row)

    rows.sort(key=lambda r: (r.get("download_date") or "", r.get("request_file") or ""))

    index_path = BASE / "_index.csv"
    snapshots_dir = BASE / "_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f"_index_{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.csv"

    fieldnames = [
        "download_date",
        "timestamp_local",
        "url",
        "what",
        "where",
        "results_per_page",
        "sort_by",
        "what_exclude",
        "count",
        "n_results",
        "request_file",
        "response_file",
    ]

    def write(path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    write(index_path)
    write(snapshot_path)

    print(f"Wrote: {index_path}")
    print(f"Wrote: {snapshot_path}")
    print(f"Indexed response files: {len(response_files)}")
    print(f"Indexed rows written:   {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
