import yaml

from ollama_client import ollama_chat
from tool_executor import load_registry, call_tool, tools_for_ollama


def main():
    # 1) Load agent config (model + base URL)
    cfg = yaml.safe_load(open("configs/agent.yaml", encoding="utf-8"))
    ollama_base = cfg["ollama"]["base_url"]
    model = cfg["ollama"]["model"]
    temperature = cfg["ollama"].get("temperature", 0.2)
    api_base = cfg["api"]["base_url"]


    # 2) Load tool registry and convert it into "tools" format for Ollama
    tools_list = load_registry()
    tools = tools_for_ollama(tools_list)
    by_id = {t["id"]: t for t in tools_list}

    print("Tools available to the agent:", [t["id"] for t in tools_list])

    # 3) Ask ONE question and let the model decide a tool call
    question = input("User question: ").strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a tool-using assistant. "
                    "If a tool can answer, call exactly one tool. "
                    "Use only the provided tools. Do not invent data."
                ),
            },
            {"role": "user", "content": question},
        ],
        "tools": tools,
        "stream": False,
        "options": {"temperature": temperature},
    }

    out = ollama_chat(ollama_base, payload)

    # 4) Print only the tool call part (this is what we’ll execute in the next step)
    msg = out.get("message", {})
    tool_calls = msg.get("tool_calls") or []
    print("\nModel tool_calls:")
    print(tool_calls)

    if not tool_calls:
        print("\nNo tool call produced.")
        return

    call = tool_calls[0]
    fn = call["function"]
    tool_id = fn["name"]
    args = fn.get("arguments", {}) or {}

    if tool_id not in by_id:
        print(f"\nTool '{tool_id}' not found in configs/tools.yaml")
        return

    tool = by_id[tool_id]
    result = call_tool(api_base, tool, params=args if args else None)

    rows = result.get("rows", [])
    print(f"\nCalled: GET {tool['endpoint']} params={args}")
    print(f"Rows returned: {len(rows)}")



if __name__ == "__main__":
    main()
