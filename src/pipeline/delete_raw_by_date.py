import argparse
import os
import shutil
import stat
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_BASE = PROJECT_ROOT / "data" / "raw" / "adzuna" / "de" / "jobs_search"


def parse_date_folder(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def remove_readonly(func, path, exc_info):
    # Windows helper for read-only files/folders during rmtree
    os.chmod(path, stat.S_IWRITE)
    func(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete raw Adzuna date folders older than a cutoff date."
    )
    parser.add_argument(
        "--before",
        required=True,
        help="Delete raw date folders strictly before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually delete folders. Without this flag, only print the deletion plan.",
    )
    args = parser.parse_args()

    cutoff = date.fromisoformat(args.before)

    if not RAW_BASE.exists():
        raise SystemExit(f"Raw base folder not found: {RAW_BASE}")

    date_dirs: list[tuple[date, Path]] = []
    for p in RAW_BASE.iterdir():
        if not p.is_dir():
            continue
        d = parse_date_folder(p.name)
        if d is not None:
            date_dirs.append((d, p))

    date_dirs.sort(key=lambda x: x[0])
    to_delete = [(d, p) for d, p in date_dirs if d < cutoff]

    print(f"Raw base: {RAW_BASE}")
    print(f"Cutoff date: {cutoff.isoformat()}")
    print(f"Date folders found: {len(date_dirs)}")
    print(f"Date folders to delete: {len(to_delete)}")

    for d, p in to_delete:
        print(f"- {d.isoformat()} -> {p.relative_to(PROJECT_ROOT).as_posix()}")

    if not args.run:
        print("\nDry run only. Use --run to actually delete.")
        return 0

    for _, p in to_delete:
        shutil.rmtree(p, onerror=remove_readonly)

    print(f"\nDeleted {len(to_delete)} raw date folder(s).")
    print("Next: rebuild raw index, overwrite processed data with the retained raw window, then reload DuckDB.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())