import yaml
from ollama_client import ollama_chat


def main():
    cfg = yaml.safe_load(open("configs/agent.yaml", encoding="utf-8"))
    base_url = cfg["ollama"]["base_url"]
    model = cfg["ollama"]["model"]
    temperature = cfg["ollama"].get("temperature", 0.2)

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Reply with just the word OK."}
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }

    out = ollama_chat(base_url, payload)
    # Ollama returns the assistant message under out["message"]["content"]
    print(out["message"]["content"])


if __name__ == "__main__":
    main()
