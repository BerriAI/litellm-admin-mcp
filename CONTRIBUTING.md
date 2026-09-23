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

Release a reviewed commit by updating the package version, running CI, building
with `uv build`, and attaching the wheel and source distribution to a matching
GitHub tag. Client integrations should pin a release or commit. PyPI publishing
can be added through the organization's trusted publishing configuration.
