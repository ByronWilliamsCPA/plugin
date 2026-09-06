---
name: fastapi-expert-extras
description: >
  Local delta on top of the vendored fastapi-expert skill. Adds a mandatory
  source-reading step before authoring an OpenAPI spec, and the Protocol-based
  structural-typing pattern for parallel-module contracts. Use alongside
  fastapi-expert when documenting an existing API, writing a spec from a brief, or
  designing a contract between two modules built in parallel. Triggers on: openapi
  spec, document existing api, route inventory, parallel module contract, Protocol
  typing, decouple modules, structural typing.
user-invocable: true
---

# fastapi-expert-extras

Extends the vendored `fastapi-expert` skill (read-only, symlinked into
`.submodules`). Contains only the delta. Load alongside `fastapi-expert`.

## Read the route source before writing the OpenAPI spec (obs 35)

For API documentation, the source code is the ground truth; the brief is context
only. Briefs routinely disagree with the running app (wrong status payloads,
described routes that do not exist, real routes the brief omits). Writing a spec
from a brief alone produces a spec that is wrong on multiple endpoints and
misleads consumers.

Mandatory step BEFORE drafting a single spec line: build a route inventory from
the source. Grep for the framework's route annotations and enumerate every route,
method, and response shape:

- FastAPI: `@router.*`, `@app.(get|post|put|delete|patch)`
- Flask: `@app.route`, blueprint `@bp.route`

Verify every route against the actual implementation. A two-minute source read
prevents an incorrect spec.

## Protocol structural typing for parallel-module contracts (obs 339)

When two modules are built in parallel against a shared contract, the consuming
module should define a `Protocol` for the fields it reads rather than importing the
producer. Importing the producer couples build order and breaks parallel
development.

Pattern:

1. In the consuming module, define a `Protocol` mirroring only the fields it reads
   from the producer's dataclass.
2. The producer satisfies the protocol structurally (no explicit `implements`, no
   import of the producer in the consumer).
3. Tests construct `SimpleNamespace` objects that also satisfy the protocol,
   enabling exact assertions without running the real producer.

This decouples build order, enables synthetic test fixtures, and lets integration
proceed unchanged when the real producer is wired in.
