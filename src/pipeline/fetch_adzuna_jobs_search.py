import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def next_seq(folder: Path, prefix: str) -> int:
    if not folder.exists():
        return 1
    existing = sorted(folder.glob(f"{prefix}_*.json"))
    if not existing:
        return 1
    last = existing[-1].stem.split("_")[-1]
    try:
        return int(last) + 1
    except ValueError:
        return len(existing) + 1


def parse_kv(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError("Expected KEY=VALUE")
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip()
    if not k:
        raise argparse.ArgumentTypeError("Empty KEY in KEY=VALUE")
    return k, v


def main() -> int:
    load_dotenv()

    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    country = os.getenv("ADZUNA_COUNTRY", "de")

    if not app_id or not app_key:
        raise SystemExit("Missing ADZUNA_APP_ID / ADZUNA_APP_KEY in .env")

    parser = argparse.ArgumentParser(
        description="Download raw Adzuna job ads (store request params + raw JSON response)."
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--results_per_page", type=int, default=20)
    parser.add_argument("--what", type=str, default=None)
    parser.add_argument("--where", type=str, default=None)

    # IMPORTANT: only send sort_by if user explicitly sets it
    parser.add_argument("--sort_by", type=str, default=None)

    # Pass-through for any additional API filters you want to try (KEY=VALUE)
    parser.add_argument("--param", action="append", type=parse_kv, default=[])

    parser.add_argument("--print_request", action="store_true", help="Print final URL + params and exit")
    args = parser.parse_args()

    base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{args.page}"

    params: dict[str, str | int] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": args.results_per_page,
    }
    if args.what is not None:
        params["what"] = args.what
    if args.where is not None:
        params["where"] = args.where
    if args.sort_by is not None:
        params["sort_by"] = args.sort_by

    # extra pass-through params
    for k, v in args.param:
        params[k] = v

    if args.print_request:
        safe_params = {k: v for k, v in params.items() if k not in {"app_id", "app_key"}}
        print("URL:", base_url)
        print("Params:", json.dumps(safe_params, ensure_ascii=False, indent=2))
        return 0

    run_date = datetime.now().strftime("%Y-%m-%d")
    out_dir = out_dir = PROJECT_ROOT / "data" / "raw" / "adzuna" / "de" / "jobs_search" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)

    seq = next_seq(out_dir, "response")
    req_file = out_dir / f"request_{seq:03d}_params.json"
    res_file = out_dir / f"response_{seq:03d}.json"

    with req_file.open("w", encoding="utf-8") as f:
        json.dump(
            {"url": base_url, "params": params, "timestamp_local": datetime.now().isoformat(timespec="seconds")},
            f,
            ensure_ascii=False,
            indent=2,
        )

    r = requests.get(base_url, params=params, timeout=60, headers={"Accept": "application/json"})
    r.raise_for_status()

    with res_file.open("w", encoding="utf-8") as f:
        f.write(r.text)

    print(f"Saved request:  {req_file}")
    print(f"Saved response: {res_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
