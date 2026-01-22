import json
import urllib.request
from urllib.parse import urlencode

BASE_URL = "http://127.0.0.1:8000"


def get(path: str, params: dict | None = None) -> dict:
    """Simple GET request helper (standard library only)."""
    url = BASE_URL + path
    if params:
        url += "?" + urlencode(params)
    with urllib.request.urlopen(url) as resp:
        return json.load(resp)


def main():
    print("Choose a tool:")
    print("  1) Replication across cities")
    print("  2) Geo by channel (Bundesland)")
    print("  3) Glossary / definitions")

    choice = input("Enter 1/2/3: ").strip()

    if choice == "3":
        data = get("/definitions")
        print("\nDefinitions:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("\nSource: GET /definitions")
        return

    if choice == "1":
        min_locations = input("Minimum number of locations for a post? (default 2): ").strip()
        limit = input("How many rows to show? (default 10): ").strip()

        params = {}
        if min_locations:
            params["min_locations"] = int(min_locations)

        show_n = int(limit) if limit else 10

        data = get("/insights/replication-across-cities", params=params if params else None)
        rows = data.get("rows", [])
        print(f"\nRows returned: {len(rows)}")
        print(f"Showing first {min(show_n, len(rows))}:")
        for r in rows[:show_n]:
            print(f"- {r.get('company')} | locations={r.get('distinct_locations')} | postings={r.get('postings')} | {r.get('sample_title')}")
        print(f"\nSource: GET /insights/replication-across-cities params={params}")
        return

    if choice == "2":
        channel = input("channel (default - All channel): ").strip()
        params = {"channel": channel} if channel else None

        data = get("/insights/geo-by-channel", params=params)
        rows = data.get("rows", [])
        print(f"\nRows returned: {len(rows)}")
        print("Top 10:")
        for r in rows[:10]:
            print(f"- {r.get('channel')} | {r.get('bundesland')} | jobs={r.get('jobs')}")
        print(f"\nSource: GET /insights/geo-by-channel params={params if params else {}}")
        return

    print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
