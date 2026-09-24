"""Synthetic response measurements; no gateway, credentials or inference calls.

Run: python scripts/benchmark_efficiency.py
Optionally install tiktoken to include o200k_base comparison counts. These are
payload measurements, not claims about startup billing or agent task quality.
"""
import json

from litellm_admin_mcp.results import ResultStore, encode, page

try:
    import tiktoken
    tokenizer = tiktoken.get_encoding("o200k_base")
except ImportError:
    tokenizer = None


keys = [{"id": f"key-{n}", "alias": f"project-{n}", "max_budget": 100,
         "spend": n / 10, "blocked": False, "expires": None,
         "models": ["example-model"], "metadata": {f"setting-{i}": f"value-{n}-{i}" for i in range(30)}}
        for n in range(123)]
fixtures = {
    "user_with_relations": {"user_id": "example-admin", "user_info": {
        "user_id": "example-admin", "user_role": "proxy_admin", "max_budget": None,
        "spend": 0, "blocked": False, "metadata": {"custom_setting": "preserved"}},
        "keys": keys, "teams": [{"id": f"team-{i}", "keys": keys[i:i + 8]} for i in range(14)]},
    "teams_with_keys": [{"id": f"team-{i}", "max_budget": None, "spend": i,
                         "keys": keys[i:i + 8]} for i in range(14)],
    "request_history": {"request_id": "example-request", "request": {"input": [
        {"role": "user", "content": f"Message {i}: " + "Example context. " * 100} for i in range(199)]},
        "response": "Example answer", "metadata": {"rare_debugging_field": False}},
}


def measure(value):
    raw = encode(value)
    return {"bytes": len(raw), **({"comparison_tokens": len(tokenizer.encode(raw.decode()))} if tokenizer else {})}


def reconstruct(item, token, path="", outputs=None):
    outputs = outputs if outputs is not None else []
    current = page(item, token, path=path)
    typ = current["type"]
    result = {} if typ == "object" else [] if typ == "array" else "" if typ == "string" else current["value"]
    while True:
        outputs.append(current)
        if typ in {"object", "array"}:
            for entry in current["entries"]:
                value = entry["value"] if entry["complete"] else reconstruct(item, token, entry["path"], outputs)
                if typ == "object":
                    result[entry["key"]] = value
                else:
                    result.append(value)
        elif typ == "string":
            result += current["value"]
        if current.get("next") is None:
            return result
        args = {k: v for k, v in current["next"].items() if k != "result_id"}
        current = page(item, token, **args)


if __name__ == "__main__":
    results = {}
    for name, original in fixtures.items():
        store = ResultStore()
        token = store.put(name, original, "synthetic-caller", "synthetic-admin")
        item = store.get(token, "synthetic-caller", "synthetic-admin")
        outputs = []
        assert reconstruct(item, token, outputs=outputs) == original
        totals = {key: sum(measure(p)[key] for p in outputs) for key in measure(outputs[0])}
        results[name] = {"original": measure(original), "first_page": measure(outputs[0]),
                         "complete_paged_retrieval": totals, "pages_for_every_field": len(outputs),
                         "exact_reconstruction": True}
    print(json.dumps({"tokenizer": "o200k_base" if tokenizer else None, "synthetic_only": True,
                      "note": "Reading every field includes index/preview overhead; small first pages do not prove task savings.",
                      "results": results}, indent=2))
