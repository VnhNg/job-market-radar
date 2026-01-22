import yaml
from ollama_client import ollama_chat
from tool_registry import load_tool_registry, tools_for_ollama


def main():
    cfg = yaml.safe_load(open("configs/agent.yaml", encoding="utf-8"))
    base_url = cfg["ollama"]["base_url"]
    model = cfg["ollama"]["model"]
    temperature = cfg["ollama"].get("temperature", 0.2)

    registry = load_tool_registry("configs/tools.yaml")
    tools = tools_for_ollama(registry)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a tool-using assistant. "
                "When a tool can answer the question, call exactly one tool. "
                "Do not invent data."
            ),
        },
        {"role": "user", "content": "Which companies repost the same role across multiple cities?"},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"temperature": temperature},
    }

    out = ollama_chat(base_url, payload)
    print(out)  # for now, print whole response so we can inspect tool call structure


if __name__ == "__main__":
    main()
