import json
import urllib.request


def ollama_chat(base_url: str, payload: dict) -> dict:
    """
    Call Ollama /api/chat and return the parsed JSON response.
    """
    url = base_url.rstrip("/") + "/api/chat"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)
