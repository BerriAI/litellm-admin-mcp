"""Build bounded MCP inputs from the gateway's own OpenAPI schemas."""
from copy import deepcopy
from typing import Any


class SchemaError(ValueError):
    pass


def resolve(spec: dict, value: dict) -> dict:
    seen = set()
    while "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/components/") or ref in seen:
            raise SchemaError("Unsupported OpenAPI reference")
        seen.add(ref)
        target: Any = spec
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise SchemaError("Missing OpenAPI reference") from None
        if not isinstance(target, dict):
            raise SchemaError("Invalid OpenAPI reference")
        value = {**target, **{k: v for k, v in value.items() if k != "$ref"}}
    return value


def tool_schema(spec: dict, path_item: dict, operation: dict) -> dict:
    groups: dict[str, dict] = {}
    # Operation-level parameters override matching path-level parameters.
    parameters = {}
    for raw in path_item.get("parameters", []) + operation.get("parameters", []):
        param = resolve(spec, raw)
        if param.get("in") in {"path", "query"}:
            parameters[(param["in"], param["name"])] = param
    for (location, name), param in parameters.items():
        group = groups.setdefault(location, {"type": "object", "properties": {}, "additionalProperties": False})
        group["properties"][name] = deepcopy(param.get("schema", {"type": "string"}))
        if location == "path" or param.get("required"):
            group.setdefault("required", []).append(name)
    required = [name for name, group in groups.items() if group.get("required")]
    if "requestBody" in operation:
        body = resolve(spec, operation["requestBody"])
        media = body.get("content", {}).get("application/json")
        if not media:
            raise SchemaError("Administrative tools require JSON request bodies")
        groups["body"] = deepcopy(media.get("schema", {"type": "object"}))
        if body.get("required"):
            required.append("body")
    root = {"type": "object", "properties": groups, "additionalProperties": False}
    if required:
        root["required"] = required

    # Preserve recursive schemas while including only reachable definitions.
    definitions = {}

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, child in value.items():
            if key == "$ref":
                if not isinstance(child, str) or not child.startswith("#/components/schemas/"):
                    raise SchemaError("Only local schema references are supported")
                pointer = child.removeprefix("#/components/schemas/")
                name = pointer.replace("~1", "/").replace("~0", "~")
                if name not in definitions:
                    definitions[name] = {}
                    try:
                        target = spec["components"]["schemas"][name]
                    except KeyError:
                        raise SchemaError("Missing schema definition") from None
                    definitions[name] = rewrite(target)
                result[key] = "#/$defs/" + pointer
            elif key != "nullable":
                result[key] = rewrite(child)
        if value.get("nullable"):
            result = {"anyOf": [result, {"type": "null"}]}
        return result

    result = rewrite(root)
    if definitions:
        result["$defs"] = definitions
    return result
