# Security

The server targets one operator-configured gateway. A tool cannot change that
target, invent an administrative route, forward arbitrary headers, or follow an
HTTP redirect. It exposes only reviewed operations present in the gateway's spec.

Local stdio runs with the administrator's configured gateway credential. Hosted
HTTP requests require each caller's own bearer credential; the server refuses
to start HTTP mode with a process-wide gateway key. The gateway's live proxy-admin
role is checked for discovery, before execution and before returning results.
The caller's own key remains the execution identity and audit actor.

Read-only mode and the tool allowlist are enforced by the server, including on
direct calls to tools hidden from discovery. Model-returned provider parameters
are restricted to model and credential-name identifiers. New virtual keys are
returned to the requesting client; administrators must trust their chosen client
to handle those results. The connector does not send prompts to a model.

Administrative writes require care from the calling agent. Tool annotations and
instructions describe mutations, but client confirmations are not an authorization
boundary. A write timeout can occur after the gateway committed a change. Requests
are never automatically retried, and there is no persistent replay journal in this
server. The LiteLLM Admin Agent maintains its own request journal.

Terminate TLS at a trusted proxy for remote deployment. Exclude authorization
headers and request/response bodies from proxy logs. The process logs no tool
arguments or results. Credentials are neither persisted nor placed in URLs.

Report vulnerabilities using this repository's private Security Advisories when
available or your established private contact with Berri AI. Do not include live
credentials in public issues.
