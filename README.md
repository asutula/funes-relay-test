# Funes Relay pilot

A real server API and Python client built by separate agents using a shared contract and Relay handoffs.

This repository contains the test feature and the Relay 0.2 prototype in `tools/relay`. The initial API contract is `api/openapi.json`. All payment records are fictional test fixtures.

## Feature interfaces

- Server: `server/payments_api.py`, exposing `create_server(host="127.0.0.1", port=0, payments=None)`. Return an HTTPServer-compatible object. When a payments list is supplied, retain that list so integration tests can insert records between requests. A command-line entry point accepts `--port` and `--fixture`.
- Client: `client/payments_client.py`, exposing `list_payments(base_url, page_size=2)`. Return the combined payment records from every response page.
- Both implementations use Python 3.11+ and the standard library.

Each component has its own tests. Integration tests exercise the client against the running server, with code and contract revisions recorded in Relay.

## Pilot sequence

1. Server and client agents implement the pinned initial contract in separate checkouts.
2. Record their contributions and baseline integration results.
3. Change the server contract in response to an observed behavior.
4. Have the client agent read Relay's shared-feature context before adapting its implementation.
5. Record the exact implementation revisions and integration results.

The evaluation asks whether the client agent can identify the changed assumptions, recover the rationale, and choose the required work from shared evidence.

## Relay

```sh
python3 tools/relay/relay.py --help
python3 -m unittest discover -s tools/relay/tests -v
```

For Relay tests, set `PYTHONPATH=tools/relay` or run them from `tools/relay`. See `tools/relay/docs/shared-features.md` for contribution metadata and commands. Shared Funes memory requires a separately configured Hugging Face dataset and authentication. Local bundles and credentials are not part of this repository.

