# Contributing

Open a pull request with the behavior change and its tests. Python 3.12 is the
tested runtime. Run `uv pip install -e '.[test]'` and `uv run --extra test pytest` before
submitting; CI also builds the distribution and container.

To add an operation, update `src/litellm_admin_mcp/operations.json` with its exact
gateway path, HTTP method, OpenAPI operation ID and a stable, unique MCP name.
Use the live gateway spec as evidence. Do not add a generic arbitrary-request tool.

Test execution with the caller's credential, rejection for unauthorized callers,
read-only enforcement, uncertain write outcomes and sensitive-result handling.
Test schema changes with referenced request models, path/query arguments and the
MCP protocol rather than only calling an internal function.

Favor functionality over compaction. Keep complete small records, expose all
advanced parameters and preserve every sanitized field in detail reads. Test
exact reconstruction from the public index/continuations, including unknown
metadata, Unicode, null/zero/false and changing source data. A shorter first
response is not sufficient evidence of a better agent workflow. Compare complete
tasks and account for schema lookups and follow-up reads; do not claim model task
parity from deterministic protocol tests alone.

The `read_only_override` catalog field is for reviewed exceptions such as POST
reads. Do not classify an operation as read-only merely to reduce friction:
`check_key_health`, for example, can emit callback test logs.

Release a reviewed commit by updating the package version, running CI, building
with `uv build`, and attaching the wheel and source distribution to a matching
GitHub tag. The default client launcher tracks `main` and refreshes the connector
on each start, so merged changes do not require a version bump to reach those
clients. Fixed deployments can pin a release or commit instead. PyPI publishing
can be added through the organization's trusted publishing configuration.
