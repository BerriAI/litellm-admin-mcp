# LiteLLM Admin MCP

Connect an agent to your LiteLLM gateway to create keys, add model deployments,
manage teams and budgets, and inspect spending.

**Currently, this MCP requires a `proxy_admin` identity for all tools, including read-only tools.**

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

Set `LITELLM_ADMIN_READ_ONLY=true` to expose only GET operations. Optionally set
`LITELLM_ADMIN_TOOLS=create_key,list_keys,list_teams` to restrict the catalog.
The gateway still enforces each caller's permissions and feature entitlements.

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
uv build
docker build -t litellm-admin-mcp:smoke .
python scripts/smoke_container.py
```

Tests use real MCP sessions with instrumented gateway fixtures; they do not call
an LLM or modify a production gateway. See [SECURITY.md](SECURITY.md) for the
credential boundary and [CONTRIBUTING.md](CONTRIBUTING.md) for adding tools.

## License

MIT. See [LICENSE](LICENSE). The initial tool inventory and authorization behavior
were extracted from Berri AI's LiteLLM Admin Agent.
