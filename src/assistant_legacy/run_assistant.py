import json
from pathlib import Path
import urllib.request
from urllib.parse import urlencode
import yaml

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_PATH = PROJECT_ROOT / "configs" / "tools.yaml"

def load_tools() -> list[dict]:
    data = yaml.safe_load(TOOLS_PATH.read_text(encoding="utf-8"))
    return data.get("tools", [])

def http_get(endpoint: str, params: dict | None = None) -> dict:
    url = BASE_URL + endpoint
    if params:
        url += "?" + urlencode(params)
    with urllib.request.urlopen(url) as resp:
        return json.load(resp)

def prompt_params(tool: dict) -> dict | None:
    spec = tool.get("params", [])
    if not spec:
        return None

    params: dict = {}
    print("\nEnter parameters (press Enter to accept default):")

    for p in spec:
        name = p["name"]
        ptype = p.get("type", "str")
        default = p.get("default", "")
        help_text = p.get("help", "")

        prompt = f"- {name} ({ptype})"
        if help_text:
            prompt += f" | {help_text}"
        if default != "":
            prompt += f" [default={default}]"
        prompt += ": "

        raw = input(prompt).strip()
        if raw == "":
            raw = str(default) if default != "" else ""

        # If still blank and not required, skip sending the param
        required = bool(p.get("required", False))
        if raw == "" and not required:
            continue
        if raw == "" and required:
            print(f"Missing required param: {name}")
            return None

        # Type conversion
        try:
            if ptype == "int":
                params[name] = int(raw)
            elif ptype == "float":
                params[name] = float(raw)
            else:
                params[name] = raw
        except ValueError:
            print(f"Invalid value for {name}. Expected {ptype}.")
            return None

    return params if params else None

def main():
    tools = load_tools()
    if not tools:
        print(f"No tools found in {TOOLS_PATH}")
        return

    print("Choose a tool:")
    for i, t in enumerate(tools, start=1):
        print(f"  {i}) {t['title']}")

    choice = input("Enter number: ").strip()
    if not choice.isdigit():
        print("Invalid input.")
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(tools):
        print("Out of range.")
        return

    tool = tools[idx]
    params = prompt_params(tool)
    if tool.get("params") and params is None and any(p.get("required", False) for p in tool["params"]):
        return

    result = http_get(tool["endpoint"], params=params)

    print("\nResult:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSource: {tool['method']} {tool['endpoint']} params={params if params else {}} (tool_id={tool['id']})")

if __name__ == "__main__":
    main()