# LiteLLM Admin MCP

Connect an agent to your LiteLLM gateway to create keys, add model deployments,
manage teams and budgets, and inspect spending.

This is a standalone MCP server. It calls your gateway's management API using
your own proxy-admin credential. Your MCP client supplies the agent and model.

## Connect from a local MCP client

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and add this
server to a client that supports local MCP processes:

```json
{
  "mcpServers": {
    "litellm-admin": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/BerriAI/litellm-admin-mcp.git@v0.1.0",
        "litellm-admin-mcp"
      ],
      "env": {
        "LITELLM_BASE_URL": "https://your-gateway.example.com",
        "LITELLM_API_KEY": "<your-personal-proxy-admin-key>"
      }
    }
  }
}
```

Use your client's secret storage if available, and keep its configuration private.
The connector requires Python 3.12 or later; uv can install a compatible Python.

Try:

- “List my teams and their budgets.”
- “Create a key for Engineering with a $100 monthly budget.”
- “Add a model named support-chat using openai/gpt-4.1 and the gateway credential openai-production.”

An admin identity is required. Creating a deployment also requires a database,
`STORE_MODEL_IN_DB=True`, the exact provider/model ID and provider authentication
configured on the gateway. Use stored credential names or gateway environment
references; keep provider secrets out of chat. Adding a gateway model does not
provision provider-side access or test inference.

## What it exposes

The [reviewed catalog](src/litellm_admin_mcp/operations.json) contains 65 operations:

- Models: add a deployment, list deployments and look up a deployment.
- Keys: create, inspect, update, rotate, block, unblock and delete keys.
- Teams: create and update teams, manage members, model access and permissions.
- Budgets: create, inspect, update and delete budgets.
- Reporting: inspect users, organizations, spending, activity and request logs.
- Team configuration: inspect and manage callbacks and logging settings.

The connector discovers request schemas from your gateway's `/openapi.json`.
Only reviewed routes available on that gateway are exposed. A changed operation
ID fails discovery until the connector is updated. Tools have stable names such
as `create_key`, `add_model`, `list_teams` and `update_budget`; their arguments are
grouped into `body`, `query` and `path` to avoid ambiguous parameter names.

Set `LITELLM_ADMIN_READ_ONLY=true` to expose only reviewed read operations (including
the POST reads `get_budgets` and `get_organization_legacy`). Optionally set
`LITELLM_ADMIN_TOOLS=create_key,list_keys,list_teams` to restrict the catalog.
The gateway still enforces each caller's permissions and feature entitlements.

## Efficient results and tool discovery

The default keeps small results complete and pages large results. All 65 actions,
advanced arguments and previously accessible result fields remain available.
There are two additional read-only tools: `describe_admin_tool` and
`read_admin_result`.

### Results: complete records, then exact detail reads

Results up to 16 KB of compact JSON are returned whole. Larger results return an
index with complete small values, useful record previews, unread field counts,
and exact `read` / `next` arguments for `read_admin_result`. This uses structural
paging, not a whitelist of "important" fields or an AI-generated summary.
Unknown metadata, `null`, `0`, `false`, empty arrays and empty objects are preserved.
A preview with `complete: false` is not the entire record; read the relevant
omitted fields before drawing conclusions. For example, a user profile can stay
complete while its embedded keys and teams are read separately.

To retrieve detail, call `read_admin_result` with the returned `read` arguments.
Follow `next` to enumerate every object field or array item. Paths are JSON
Pointers supplied by the index; string chunks use Unicode code-point offsets.
To retrieve the entire original result in one response, use its `full_read`
arguments (an empty path selects the root):

```json
{"result_id": "<returned-result-id>", "path": "", "view": "full"}
```

These reads use the same saved result, even if gateway data changes. Reading a
write's result never repeats the write. **Do not repeat a create, rotate or delete
operation just to request a different response view.** Newly created/rotated keys
are always delivered inline in the full result and are never cached.

Every administrative tool also accepts `response: {"view": "full"}` to request
an inline result on its initial call. Set `LITELLM_ADMIN_RESPONSE_VIEW=full` to make
that the process default. Neither setting changes the gateway query, its scope,
or the existing secret-redaction rules.

Snapshots are bound to both the caller's credential and current admin identity,
and expire after five minutes. Each read rechecks authorization before releasing
data. The in-memory store admits at most 16 snapshots per credential and 64 MB of
serialized data in total; it never evicts an unexpired result to make room. When
full, or when a result contains recognizable credentials, the original complete
response is returned inline instead. Expired entries are removed on the next
cache access; shutdown clears the store. HTTP deployments with multiple workers
must route subsequent result reads to the same process. A missing/expired result
does not authorize repeating a write.

Collection pages target 16 KB plus index overhead, up to 20 entries by default;
large individual fields remain explicitly retrievable. Administrative calls
stream at most 16 MB from the gateway in either view, replacing the previous
2 MB limit checked after downloading the entire response. Use upstream pagination
or filters for larger queries. Explicit full reads can be large: request pages
if the client has an output limit.

### Tool search: use the client's native discovery

By default, the server publishes ordinary named MCP tools with their complete
input schemas and individual safety annotations. A client such as Codex can use
native tool search/deferred loading with this interface; no custom dispatcher or
second schema lookup is required. The client controls whether definitions enter
model context eagerly or on demand. The size of `tools/list` is not a measurement
of initial model tokens. See OpenAI's [tool search documentation](https://developers.openai.com/api/docs/guides/tools-tool-search).

For a client that loads every schema upfront, an optional fallback is available:

```sh
export LITELLM_ADMIN_SCHEMA_MODE=discovery
```

This keeps all original tool names, descriptions, required argument groups and
safety annotations, while deferring parameter detail. Before an operation, the
agent calls `describe_admin_tool` with its exact name to obtain **every** supported
argument, constraint, default, example and referenced definition, then calls the
original named tool. Execution still validates the complete gateway schema.
This mode intentionally uses permissive argument declarations; it is not native
tool search and adds a schema lookup. Prefer the default `full` schema mode when
the client already supports native tool search. The helper can also page an
unusually large schema with `response: {"view": "compact"}`.

The tool allowlist and read-only policy apply to discovery and direct execution
in both modes. Helpers cannot invoke administrative operations or arbitrary URLs.

## Host an HTTP connector

For remote clients, run the same package with Streamable HTTP:

```sh
export LITELLM_BASE_URL=https://your-gateway.example.com
export LITELLM_MCP_PUBLIC_URL=https://admin-mcp.example.com
uvx --from git+https://github.com/BerriAI/litellm-admin-mcp.git@v0.1.0 \
  litellm-admin-mcp --transport streamable-http --port 8080
```

Put an HTTPS reverse proxy in front of port 8080. The MCP endpoint is `/mcp` and
the process health endpoint is `/healthz`. The public URL configures accepted
Host and Origin values. One installation connects to one trusted gateway.

Do **not** set `LITELLM_API_KEY` on the hosted server. Every client supplies its
own personal gateway credential:

```json
{
  "mcpServers": {
    "litellm-admin": {
      "url": "https://admin-mcp.example.com/mcp",
      "headers": {"Authorization": "Bearer <your-personal-proxy-admin-key>"}
    }
  }
}
```

Client configuration varies; use a client that supports Streamable HTTP and
bearer headers. This release uses API-key authentication, not a browser OAuth
installation flow. Admin status is checked against the gateway on every request
and before releasing tool results. No shared admin credential is stored by the
HTTP service.

Docker is also supported:

```sh
docker build -t litellm-admin-mcp .
docker run --rm -p 127.0.0.1:8080:8080 \
  -e LITELLM_BASE_URL=https://your-gateway.example.com \
  -e LITELLM_MCP_PUBLIC_URL=https://admin-mcp.example.com \
  litellm-admin-mcp
```

## Using it from the LiteLLM Admin Agent

The [LiteLLM Admin Agent](https://github.com/BerriAI/litellm-admin-agent) can use
this server as its tool provider. The connector owns the admin API integration;
the agent owns the conversation, Slack interface and user sign-in. Other MCP
clients can use this connector independently.

The package exports `litellm_admin_mcp.catalog.OPERATIONS` for clients that need
the reviewed tool metadata. Clients should discover live tool schemas through
MCP, since endpoint availability depends on the gateway release.

## Operational notes

- Tool calls are not retried automatically. After a write timeout, inspect the
  affected gateway object before retrying. The server does not promise exactly-once writes.
- Provider parameters are filtered from model results. Creating a virtual key
  returns the new key to the authorized client; that client must handle it privately.
- Gateway and model-provider retention settings still apply to their traffic.
- `/healthz` checks the process, not gateway compatibility. Verify a read and a
  disposable create/read/delete workflow against your gateway before rollout.
- HTTPS is required for gateways except local loopback development addresses.

## Development

```sh
uv venv --python 3.12
uv pip install -e '.[test]'
uv run --extra test pytest
uv run python scripts/benchmark_efficiency.py
uv build
docker build -t litellm-admin-mcp:smoke .
python scripts/smoke_container.py
```

Tests use real MCP sessions with instrumented gateway fixtures; they do not call
an LLM or modify a production gateway. See [SECURITY.md](SECURITY.md) for the
credential boundary and [CONTRIBUTING.md](CONTRIBUTING.md) for adding tools.
The synthetic benchmark verifies exact reconstruction and reports both the first
page and the cost of retrieving every field; optional `tiktoken` installation adds
comparison token counts. It does not measure client startup context or agent
reasoning quality.

## License

MIT. See [LICENSE](LICENSE). The initial tool inventory and authorization behavior
were extracted from Berri AI's LiteLLM Admin Agent.
