"""Authenticated, non-retrying calls to a fixed LiteLLM management API."""
import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx2
import jsonschema
from mcp import types

from .catalog import BY_NAME, OPERATIONS
from .config import Config
from .schema import SchemaError, tool_schema


class AdminError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def valid_credential(value: str) -> str:
    if not value or len(value) > 8192 or any(not 33 <= ord(c) <= 126 for c in value):
        raise AdminError("A personal LiteLLM admin credential is required.", 401)
    return value


def safe_result(value: Any, credential: str) -> Any:
    """Keep new virtual keys usable, but never return provider/authentication secrets."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key.lower() == "litellm_params":
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except ValueError:
                        item = {}
                item = {k: v for k, v in item.items() if k in {"model", "litellm_credential_name"}} if isinstance(item, dict) else {}
            elif key.lower() in {"api_key", "token", "access_token", "refresh_token", "password", "secret",
                                 "client_secret", "authorization", "authentication_token", "credential_values"}:
                if not (key.lower() in {"api_key", "token"} and isinstance(item, str) and re.fullmatch(r"[a-f0-9]{64}", item)):
                    item = "[redacted]"
            result[key] = safe_result(item, credential)
        return result
    if isinstance(value, list):
        return [safe_result(item, credential) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            decoded = None
        if isinstance(decoded, (dict, list)):
            return json.dumps(safe_result(decoded, credential))
        return value.replace(credential, "[credential redacted]")
    return value


class Gateway:
    def __init__(self, config: Config, client: httpx2.AsyncClient | None = None):
        self.config = config
        self.client = client
        self._owns_client = client is None
        self._tools: dict[str, types.Tool] | None = None
        self._loaded_at = 0.0
        self._schema_lock = asyncio.Lock()

    async def __aenter__(self):
        if self.client is None:
            self.client = httpx2.AsyncClient(timeout=httpx2.Timeout(30, read=120), follow_redirects=False)
        return self

    async def __aexit__(self, *args):
        if self._owns_client and self.client is not None:
            await self.client.aclose()
            self.client = None

    async def _request(self, method: str, path: str, credential: str, **kwargs) -> Any:
        assert self.client is not None
        write = method != "GET"
        uncertain = " Check gateway state before retrying this change." if write else ""
        try:
            result = await self.client.request(method, self.config.base_url + path,
                headers={"Authorization": "Bearer " + valid_credential(credential), "Cookie": "", **kwargs.pop("headers", {})},
                follow_redirects=False, **kwargs)
        except httpx2.RequestError:
            raise AdminError("Gateway request could not be completed." + uncertain, 504) from None
        if not 200 <= result.status_code < 300:
            raise AdminError(f"Gateway returned HTTP {result.status_code}." + uncertain, result.status_code)
        if len(result.content) > 2_000_000 and path != "/openapi.json":
            raise AdminError("Result is too large; use pagination or a narrower query." + uncertain)
        try:
            return result.json()
        except ValueError:
            raise AdminError("Gateway returned an invalid JSON response." + uncertain, 502) from None

    async def authorize(self, credential: str) -> str:
        data = await self._request("GET", "/user/info", credential)
        user = data.get("user_info") if isinstance(data, dict) else None
        if (not isinstance(user, dict) or user.get("user_role") != "proxy_admin"
                or not isinstance(user.get("user_id"), str) or not user["user_id"]
                or data.get("user_id") != user["user_id"] or user.get("blocked")
                or user.get("deleted") or user.get("is_active") is False):
            raise AdminError("Only current LiteLLM proxy admins may use these tools.", 403)
        return user["user_id"]

    async def tools(self, credential: str) -> dict[str, types.Tool]:
        await self.authorize(credential)
        async with self._schema_lock:
            if self._tools is not None and time.monotonic() - self._loaded_at < 300:
                return self._tools
            spec = await self._request("GET", "/openapi.json", credential)
            if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
                raise AdminError("Gateway OpenAPI schema is unavailable.", 503)
            selected = {}
            for item in OPERATIONS:
                if self.config.allowed_tools and item.name not in self.config.allowed_tools:
                    continue
                if self.config.read_only and not item.read_only:
                    continue
                path = spec["paths"].get(item.path, {})
                operation = path.get(item.method.lower())
                if not operation:
                    continue
                if operation.get("operationId") != item.operation_id:
                    raise AdminError(f"Gateway operation changed for {item.name}; update the connector before using it.", 503)
                try:
                    schema = tool_schema(spec, path, operation)
                    jsonschema.Draft202012Validator.check_schema(schema)
                except (SchemaError, jsonschema.SchemaError, TypeError, KeyError):
                    raise AdminError(f"Gateway schema is unsupported for {item.name}.", 503) from None
                selected[item.name] = types.Tool(
                    name=item.name, description=f"{item.summary}. {item.method} {item.path}. "
                    + ("Read-only." if item.read_only else "Changes gateway state; execute only when requested. Never retry an uncertain write."),
                    inputSchema=schema, annotations=types.ToolAnnotations(
                        readOnlyHint=item.read_only, destructiveHint=not item.read_only,
                        idempotentHint=item.read_only, openWorldHint=True,
                    ),
                )
            if not selected:
                raise AdminError("No compatible, enabled admin tools were found on this gateway.", 503)
            self._tools = selected
            self._loaded_at = time.monotonic()
            return selected

    async def call(self, name: str, arguments: dict, credential: str) -> Any:
        available = await self.tools(credential)
        if name not in available:
            raise AdminError("This tool is not enabled for this connector.", 403)
        try:
            jsonschema.Draft202012Validator(available[name].input_schema).validate(arguments)
        except jsonschema.ValidationError:
            raise AdminError("Arguments do not match the discovered tool schema.") from None
        item = BY_NAME[name]
        path = item.path
        for field, value in arguments.get("path", {}).items():
            value = str(value)
            if value in {"", ".", ".."} or any(c in value for c in ("/", "\\", "%", "\r", "\n", "\x00")):
                raise AdminError("Invalid resource identifier.")
            path = path.replace("{" + field + "}", quote(value, safe=""))
        query = []
        for field, value in arguments.get("query", {}).items():
            if value is None:
                continue
            for part in value if isinstance(value, list) else [value]:
                query.append((field, json.dumps(part) if isinstance(part, (dict, bool)) else str(part)))
        principal = await self.authorize(credential)
        result = await self._request(item.method, path, credential, params=query,
            **({"json": arguments["body"]} if "body" in arguments else {}),
            headers={"litellm-changed-by": principal})
        if await self.authorize(credential) != principal:
            raise AdminError("Admin identity changed during the request. Inspect gateway state before retrying.", 403)
        return safe_result(result, credential)
