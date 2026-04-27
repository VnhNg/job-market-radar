import argparse
import csv
import json
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from text_fingerprint import load_fingerprint_config, fingerprint_md5


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_INDEX = PROJECT_ROOT / "data" / "raw" / "adzuna" / "de" / "jobs_search" / "_index.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REGISTRY_PATH = PROCESSED_DIR / "registry.jsonl"
FP_CFG = load_fingerprint_config()

def request_path_from_response(response_path: Path) -> Path:
    return response_path.with_name(
        response_path.name.replace("response_", "request_").replace(".json", "_params.json")
    )


def relpath(p: Path) -> str:
    # Store paths relative to project root, POSIX style (portable)
    return p.relative_to(PROJECT_ROOT).as_posix()


def git_commit_hash() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def _safe_json_load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _job_to_row(job: dict, *, what: str, fetched_at: Optional[str], req_file: Path, res_file: Path) -> dict:
    # Core canonical fields
    job_id = str(job.get("id", ""))
    row = {
        "source": "adzuna",
        "job_id": job_id,
        "created_at": job.get("created", ""),
        "title": job.get("title", ""),
        "company": (job.get("company") or {}).get("display_name", "") if isinstance(job.get("company"), dict) else "",
        "location": (job.get("location") or {}).get("display_name", "") if isinstance(job.get("location"), dict) else "",
        "url": job.get("redirect_url", ""),
        "description": job.get("description", ""),
    }

    # Compact “everything else” bucket
    extra: dict[str, Any] = {
        "queries": [what],
        "fetched_at": fetched_at,
        "raw_request_file": relpath(req_file),
        "raw_response_file": relpath(res_file),
        "desc_sig": fingerprint_md5(job.get("description", ""), FP_CFG),
    }

    # Optional + source-specific fields (only if present)
    loc = job.get("location")
    if isinstance(loc, dict) and isinstance(loc.get("area"), list):
        extra["location_area"] = loc["area"]

    for k in ("latitude", "longitude", "contract_time", "contract_type"):
        if k in job:
            extra[k] = job.get(k)

    cat = job.get("category")
    if isinstance(cat, dict):
        if "label" in cat:
            extra["category_label"] = cat.get("label")
        if "tag" in cat:
            extra["category_tag"] = cat.get("tag")

    # Keep adref + salary_is_predicted (explicitly requested earlier)
    if "adref" in job:
        extra["source_adref"] = job.get("adref")
    if "salary_is_predicted" in job:
        extra["source_salary_is_predicted"] = job.get("salary_is_predicted")

    row["extra_json"] = extra
    return row


def _parse_one_response(response_file_rel: str, what: str) -> list[dict]:
    res_path = PROJECT_ROOT / response_file_rel
    req_path = request_path_from_response(res_path)

    req = _safe_json_load(req_path)
    res = _safe_json_load(res_path)
    if req is None or res is None:
        return []

    fetched_at = req.get("timestamp_local")
    results = res.get("results") or []
    if not isinstance(results, list):
        return []

    rows = []
    for job in results:
        if isinstance(job, dict) and "id" in job:
            rows.append(_job_to_row(job, what=what, fetched_at=fetched_at, req_file=req_path, res_file=res_path))
    return rows


def _merge_group(g: pd.DataFrame) -> pd.Series:
    # One row per (source, job_id). Merge extra_json["queries"] by union.
    first = g.iloc[0].to_dict()

    # Parse extra_json dicts (they may already be dicts or JSON strings)
    extras: list[dict] = []
    for v in g["extra_json"].tolist():
        if isinstance(v, dict):
            extras.append(v)
        else:
            try:
                extras.append(json.loads(v) if isinstance(v, str) and v else {})
            except Exception:
                extras.append({})

    # Union queries
    qset = set()
    for ex in extras:
        qs = ex.get("queries")
        if isinstance(qs, list):
            qset.update([str(x) for x in qs if x is not None])
        elif isinstance(qs, str):
            qset.add(qs)

    # Merge extras: prefer first non-null-ish values, but always set queries to union
    merged_extra: dict[str, Any] = {}
    for ex in extras:
        for k, val in ex.items():
            if k == "queries":
                continue
            if k not in merged_extra and val not in ("", None, [], {}):
                merged_extra[k] = val

    merged_extra["queries"] = sorted(qset)
    first["extra_json"] = merged_extra
    return pd.Series(first)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract canonical job dataset from Adzuna raw files.")
    parser.add_argument("--dataset", required=True, help="Dataset name, used for output filenames (no extension).")
    parser.add_argument("--what", action="append", required=True, help="Filter by request.params.what (repeatable).")
    parser.add_argument("--mode", choices=["append", "overwrite"], default="append")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan only; do not write outputs.")
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    out_csv = PROCESSED_DIR / f"{args.dataset}.csv"
    manifest_path = PROCESSED_DIR / f"{args.dataset}.manifest.json"

    if not RAW_INDEX.exists():
        raise SystemExit(f"Missing raw index: {RAW_INDEX}. Build the raw index before extracting.")

    idx = pd.read_csv(RAW_INDEX, encoding="utf-8-sig")
    # Required columns we depend on
    required_cols = {"what", "response_file", "request_file", "n_results"}
    missing = required_cols - set(idx.columns)
    if missing:
        raise SystemExit(f"Raw index missing columns: {sorted(missing)}")

    whats = list(dict.fromkeys(args.what))  # de-dup preserve order
    idx_f = idx[idx["what"].isin(whats)].copy()

    # Build mapping response_file -> what (used to tag rows with query)
    # If the same response_file appears multiple times (shouldn't), last wins.
    res_to_what = dict(zip(idx_f["response_file"].astype(str), idx_f["what"].astype(str)))

    candidate_response_files = sorted(res_to_what.keys())

    already_processed = set()
    if args.mode == "append" and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            already_processed = set(manifest.get("raw_inputs", {}).get("response_files", []))
        except Exception:
            already_processed = set()

    if args.mode == "append":
        to_process = [rf for rf in candidate_response_files if rf not in already_processed]
    else:
        to_process = candidate_response_files

    expected_rows = int(idx_f[idx_f["response_file"].isin(to_process)]["n_results"].fillna(0).sum())

    plan = {
        "dataset": args.dataset,
        "mode": args.mode,
        "out_csv": relpath(out_csv),
        "manifest": relpath(manifest_path),
        "registry": relpath(REGISTRY_PATH),
        "filter_what": whats,
        "raw_candidates": len(candidate_response_files),
        "raw_already_processed": len(already_processed) if args.mode == "append" else None,
        "raw_to_process": len(to_process),
        "expected_rows_from_raw_index": expected_rows,
        "output_exists": out_csv.exists(),
    }

    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    # Parse new raw files (I/O-bound) in parallel
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [
            ex.submit(_parse_one_response, response_rel, res_to_what[response_rel])
            for response_rel in to_process
        ]
        for fut in as_completed(futures):
            rows.extend(fut.result())

    new_df = pd.DataFrame(rows)
    if new_df.empty and args.mode == "append" and out_csv.exists():
        print("No new raw files to process; dataset unchanged.")
        return 0

    # Load existing, append, then dedupe with query-union logic
    if args.mode == "append" and out_csv.exists():
        existing = pd.read_csv(out_csv, encoding="utf-8-sig")
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    if combined.empty:
        raise SystemExit("No rows extracted. Check your filters and raw files.")

    # Ensure required columns exist
    for col in ["source", "job_id", "extra_json"]:
        if col not in combined.columns:
            raise SystemExit(f"Internal error: missing column {col}")

    # Group-merge duplicates by (source, job_id)
    combined = combined.groupby(["source", "job_id"], as_index=False, sort=False).apply(_merge_group)
    combined = combined.reset_index(drop=True)

    # Serialize extra_json dicts back to JSON strings
    combined["extra_json"] = combined["extra_json"].apply(lambda d: json.dumps(d, ensure_ascii=False) if isinstance(d, dict) else str(d))

    # Write CSV
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    # Update manifest: track which raw response files are now included
    if args.mode == "append" and manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            prev_files = set(prev.get("raw_inputs", {}).get("response_files", []))
        except Exception:
            prev_files = set()
        final_files = sorted(prev_files.union(set(to_process)))
    else:
        final_files = sorted(set(to_process))

    commit = git_commit_hash()
    run_id = str(uuid.uuid4())
    now_iso = datetime.now().isoformat(timespec="seconds")

    manifest_obj = {
        "dataset_name": args.dataset,
        "source": "adzuna",
        "created_at": now_iso,
        "mode": args.mode,
        "filter": {"what_list": whats},
        "raw_inputs": {"response_files": final_files},
        "stats": {
            "raw_files_selected": len(to_process),
            "rows_extracted_this_run": int(len(new_df)) if not new_df.empty else 0,
            "rows_in_output": int(len(combined)),
            "unique_jobs_in_output": int(len(combined)),  # already deduped
        },
        "schema": {"columns": combined.columns.tolist()},
        "code": {"git_commit": commit, "run_id": run_id},
    }
    manifest_path.write_text(json.dumps(manifest_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append to central registry (JSONL)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry_entry = {
        "run_id": run_id,
        "timestamp": now_iso,
        "dataset_name": args.dataset,
        "dataset_csv_path": relpath(out_csv),
        "manifest_path": relpath(manifest_path),
        "mode": args.mode,
        "filter": {"what_list": whats},
        "raw_files_processed": len(to_process),
        "rows_extracted": int(len(new_df)) if not new_df.empty else 0,
        "rows_in_output": int(len(combined)),
        "git_commit": commit,
    }
    with REGISTRY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registry_entry, ensure_ascii=False) + "\n")

    print(f"Wrote CSV: {out_csv}")
    print(f"Wrote manifest: {manifest_path}")
    print(f"Appended registry: {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
