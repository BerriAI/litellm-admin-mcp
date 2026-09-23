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
    # Some clients render a referenced top-level body as `unknown`. Inline that
    # one level, preserving every field and constraint, then retain only the
    # definitions still needed (including recursive references).
    body = result["properties"].get("body", {})
    if set(body) == {"$ref"}:
        name = body["$ref"].removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
        result["properties"]["body"] = deepcopy(definitions[name])
    reachable = set()

    def visit(value):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
                if name not in reachable:
                    reachable.add(name)
                    visit(definitions[name])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    definitions = {name: value for name, value in definitions.items() if name in reachable}
    if definitions:
        result["$defs"] = definitions
    return result


def discovery_schema(schema: dict, name: str) -> dict:
    """Keep named tools/approval boundaries while deferring parameter detail.

    This fallback declaration accepts the same body/query/path shapes, including
    scalar or array bodies. Execution ALWAYS validates the complete schema.
    No constraints are guessed from a small subset of commonly used fields.
    """
    result = {"type": "object", "additionalProperties": False, "properties": {}}
    for group in schema["properties"]:
        result["properties"][group] = (deepcopy(schema["properties"][group]) if group == "response" else {
            "description": f"Before calling {name}, use describe_admin_tool with name={name} for the complete {group} schema. All original fields remain supported and are validated on execution."
        })
    if schema.get("required"):
        result["required"] = list(schema["required"])
    return result
