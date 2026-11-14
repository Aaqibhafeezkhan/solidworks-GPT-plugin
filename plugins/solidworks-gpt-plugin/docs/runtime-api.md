# Runtime knowledge-base API

The skills use the public camelCase API at `SW_KB_HOST`, defaulting to
`https://sw-plugin.erfouni.ir`. All calls must use shell `curl` with the complete
URL quoted. Runtime requests do not use an authorization header.

On Windows, run `curl.exe` instead of `curl`: in Windows PowerShell 5.1
`curl` is an alias for `Invoke-WebRequest`, which rejects curl options such
as `-sS`. `curl.exe` is the real curl in every Windows shell.

## Contents

1. [Health and catalog](#health-and-catalog)
2. [Knowledge and rules](#knowledge-and-rules)
3. [Standards](#standards)
4. [Global safeguards](#global-safeguards)
5. [Feedback](#feedback)
6. [Failure handling](#failure-handling)

## Health and catalog

```text
GET /health
GET /api/categories
GET /api/parts?categoryId={uuid}&pageSize=100
GET /api/parts?categoryId={uuid}&q={query}&pageSize=100
GET /api/parts?q={query}&pageSize=20
GET /api/parts/{partId}
```

Part list responses contain `items`, `page`, `pageSize`, and `total`. Full part
detail includes the part plus published `instructions`, `macros`,
`knownErrors`, and `lessons`.

Use instructions as the primary feature sequence. A non-template macro may be
run after substituting only declared parameters. Adapt template macros. Apply
resolved known-error fixes before calling the affected SolidWorks method.

## Knowledge and rules

```text
GET  /api/knowledge?kind=convention
GET  /api/knowledge/search?q={query}
GET  /api/knowledge/{slug}
GET  /api/design-rules
POST /api/check-context
```

Knowledge kinds are `reference`, `convention`, `playbook`, and `strategy`.
Documents may be Persian or English.

Check-context accepts known design values and ignores rules whose required
inputs are missing. Common keys are:

```json
{
  "welded": true,
  "tolerance_class": "m",
  "process": "welded_steel",
  "wall_thickness_mm": 3,
  "nominal_dimension_mm": 100,
  "fastener": "M8",
  "hole_mm": 9,
  "material": "Plain Carbon Steel"
}
```

Result statuses are `pass`, `fail`, `warn`, `advisory`, and `na`. Resolve all
fails before modeling and again before final save or export.

## Standards

```text
GET /api/standards
GET /api/standards/{table}
GET /api/standards/{table}/{key}
```

Tables include `materials`, `fits`, `clearance_holes`,
`tolerances_iso2768`, `fasteners`, `sheet_metal_gauges`,
`preferred_numbers`, `surface_finish`, `gdt_symbols`, and
`standard_metadata`. Database units are mm, MPa, and g/cm3.

## Global safeguards

```text
GET /api/errors
GET /api/lessons
```

Load both once per Codex task. Before a SolidWorks API call, match the method
against `swFeature` and apply a resolved `resolution`. Treat lesson
`prevention` values as active rules.

## Feedback

```text
POST /api/feedback
Content-Type: application/json
```

The body follows `../schemas/feedback-submission.schema.json`. `issues` and
`sessionId` are mandatory. The backend upserts on `sessionId`, so the ID must
stay fixed for the Codex task. Omit empty arrays. Code in `macros[].code` must
be the full final source.

Submission requires explicit consent unless `~/.sw-feedback-pref` contains
exactly `always`. Retry timeouts and `5xx` responses at most three times with
about two seconds between attempts. Do not retry a `4xx` response.

## Failure handling

- Offline or timeout: record the issue and continue CAD work without KB data.
- `404`: treat the requested resource as absent.
- `422`: simplify the request once, then use the fallback path.
- `5xx`: skip the failed phase and continue.

The KB is an accelerator, never a gatekeeper for the user's local CAD task.
