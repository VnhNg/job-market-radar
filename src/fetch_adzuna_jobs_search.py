import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


def next_seq(folder: Path, prefix: str) -> int:
    """Find next sequence number for files like prefix_001.json."""
    if not folder.exists():
        return 1
    existing = sorted(folder.glob(f"{prefix}_*.json"))
    if not existing:
        return 1
    # prefix_001.json -> 1
    last = existing[-1].stem.split("_")[-1]
    try:
        return int(last) + 1
    except ValueError:
        return len(existing) + 1


def main() -> int:
    load_dotenv()

    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    country = os.getenv("ADZUNA_COUNTRY", "de")

    if not app_id or not app_key:
        raise SystemExit(
            "Missing ADZUNA_APP_ID / ADZUNA_APP_KEY. Copy .env.example to .env and fill in your keys."
        )

    parser = argparse.ArgumentParser(description="Download raw Adzuna job ads (schema-safe raw JSON).")
    parser.add_argument("--page", type=int, default=1, help="Adzuna search page number (default: 1)")
    parser.add_argument("--results_per_page", type=int, default=50, help="Results per page (default: 50)")
    parser.add_argument("--what", type=str, default=None, help="Keyword query (e.g., 'data scientist')")
    parser.add_argument("--where", type=str, default=None, help="Location query (e.g., 'Berlin' or 'Germany')")
    parser.add_argument("--sort_by", type=str, default="date", help="Sort (commonly 'date' or 'relevance')")
    args = parser.parse_args()

    base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{args.page}"

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": args.results_per_page,
        "sort_by": args.sort_by,
    }
    if args.what:
        params["what"] = args.what
    if args.where:
        params["where"] = args.where

    # Create dated folder for raw downloads
    run_date = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path("data/raw/adzuna/de/jobs_search") / run_date
    out_dir.mkdir(parents=True, exist_ok=True)

    seq = next_seq(out_dir, "response")
    req_file = out_dir / f"request_{seq:03d}_params.json"
    res_file = out_dir / f"response_{seq:03d}.json"

    # Save request params (ground truth of what you asked for)
    with req_file.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "url": base_url,
                "params": params,
                "timestamp_local": datetime.now().isoformat(timespec="seconds"),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    r = requests.get(base_url, params=params, timeout=60)
    r.raise_for_status()

    # Save response raw JSON (no schema assumptions)
    with res_file.open("w", encoding="utf-8") as f:
        f.write(r.text)

    print(f"Saved request:  {req_file}")
    print(f"Saved response: {res_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
