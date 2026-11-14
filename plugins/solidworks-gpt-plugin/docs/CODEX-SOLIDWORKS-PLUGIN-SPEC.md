# SolidWorks Design Assistant — Full Spec for Building the Codex (ChatGPT) Version

> **هدف این فایل:** این سند نسخه‌ی کامل و خوداتکای پلاگین `solidworks-claude-plugin` (نسخه 1.1.7) است.
> همه‌ی APIها، ایجنت‌ها، skillها، hookها و پروتکل‌ها این‌جا آمده تا Codex بتواند **دقیقاً همین پلاگین** را
> برای ChatGPT Codex CLI بسازد. هیچ فایل دیگری لازم نیست — این سند کامل است.
>
> **Instruction to Codex:** Build an equivalent of this Claude Code plugin for the OpenAI Codex CLI.
> Everything below (architecture, prompts, API contracts, JSON schemas, protocols) is the complete
> source of truth. Section 2 explains how to map Claude-plugin concepts onto Codex.

---

## 1. What the plugin does (overview)

The plugin turns the coding agent into a **SolidWorks CAD design assistant backed by a remote
knowledge base (KB) server**. The loop is:

1. **On session start** a hook injects a protocol into the agent's context: a fixed `SESSION_ID`,
   the KB base URL, and mandatory rules.
2. **Before any SolidWorks modeling/code**, the agent runs two knowledge protocols:
   - `pre-start` — load conventions, design rules, task-relevant docs, and validate design
     parameters against the rules (`check-context`).
   - `kb-api` — look up the specific part in the catalog (published instructions, macros,
     known errors, lessons) and use them instead of inventing from scratch.
3. **Throughout the session** a `learner` component tracks everything produced: build steps,
   every code block (Python/VBA/SWAPI), concrete errors + fixes, and lessons.
4. **At session end** a `session-reporter` component builds a `FeedbackSubmission` payload,
   asks the user for consent (interactive prompt with "Yes / Always / Skip"), and POSTs it to
   `POST /api/feedback` on the KB server. The KB grows from every session.

**KB server:** `https://sw-plugin.erfouni.ir` (configurable via env var `SW_KB_HOST`).
The runtime API used by the agent is **public — no auth**. All requests are plain HTTPS + JSON.

**Critical transport rule:** the agent must call the KB with **`curl` through the shell**
(never a built-in web-fetch tool that routes through the vendor's cloud — it can't reach private
hosts). Always wrap URLs in double quotes (unquoted `?` and `&` break in zsh).

---

## 2. Mapping Claude-plugin concepts → Codex CLI

| Claude Code concept | What it is here | Codex equivalent to build |
|---|---|---|
| Plugin manifest (`plugin.json`) | name/version/skills list/`SW_KB_HOST` config | `config.toml` entry + a project or global `AGENTS.md` |
| `SessionStart` hook (bash script) | injects SESSION_ID + protocol text into context at conversation start | Put the protocol text (Section 3) into `AGENTS.md` (global `~/.codex/AGENTS.md` or project `AGENTS.md`). Generate the SESSION_ID with a tiny shell step the agent runs at first SolidWorks request (`uuidgen`), or a Codex `notify`/startup script if available. |
| Skill `pre-start` | markdown instructions loaded on demand | Custom prompt file, e.g. `~/.codex/prompts/sw-pre-start.md`, invoked as `/sw-pre-start`; ALSO summarized in AGENTS.md so the model self-triggers it |
| Skill `kb-api` | markdown instructions | `~/.codex/prompts/sw-kb-api.md` → `/sw-kb-api` |
| Skill/agent `learner` | builds the FeedbackSubmission payload from the whole conversation | `~/.codex/prompts/sw-learner.md` → `/sw-learner` |
| Skill/agent `session-reporter` | consent + POST /api/feedback | `~/.codex/prompts/sw-report.md` → `/sw-report` |
| `AskUserQuestion` interactive widget | 3-option consent UI | Codex has no widget tool — ask the consent question as the final plain-text message with the 3 options, and wait for the user's reply before POSTing |
| `~/.sw-feedback-pref` file | stores "always send" preference | identical — same file, same semantics |
| `.sw-learner-state.json` | per-project learner state | identical file in the working directory |

Everything else (API contracts, payload schemas, protocol steps) transfers verbatim.

---

## 3. Session-start protocol text (inject into every session)

This is what the SessionStart hook injects. Reproduce it (adapted names) in AGENTS.md /
system context for Codex. `{KB_HOST}` = `SW_KB_HOST` env var, default `https://sw-plugin.erfouni.ir`.
`{SESSION_ID}` = a UUIDv4 generated once per conversation and **never regenerated mid-session**.

```
You have the SolidWorks Design Plugin active (KB: {KB_HOST}).

== SESSION ID (fixed for this entire conversation) ==
SESSION_ID: {SESSION_ID}
Include this in EVERY POST /api/feedback as "sessionId". The backend upserts on
sessionId — multiple submissions update the same record. Never omit it. Never
generate a new one mid-session.

== MANDATORY PROTOCOL — RUNS ON EVERY SOLIDWORKS REQUEST ==
When the user asks you to create, build, model, or design ANYTHING in SolidWorks
(parts, assemblies, gears, shafts, housings, or any mechanical component), you
MUST run these two protocols in order before writing any code or modeling:
  1. pre-start  — loads conventions, design rules, knowledge docs, validates parameters
  2. kb-api     — looks up the specific part in the catalog
Do NOT skip these. Do NOT use generic brainstorming instead.

== LEARNER — ACTIVE FROM THE FIRST MESSAGE ==
Continuously track this session for the knowledge base:
- INSTRUCTIONS: exact ordered steps followed to build each part (corrected version only)
- MACROS: every Python/VBA/SWAPI code block written — full source, final working version
- KNOWN ERRORS: concrete failures with exact SW API method and resolution
- LESSONS: non-obvious patterns and rules (successes AND failures)

== HOW TO CALL THE KB SERVER ==
ALWAYS use curl via the shell. NEVER use a built-in fetch tool.
Always wrap URLs in double quotes — unquoted ? and & fail in zsh.

== END OF EVERY SOLIDWORKS SESSION (MANDATORY) ==
After completing the model and giving the user the result, run session-reporter:
  - Check the "always send" preference (~/.sw-feedback-pref) — auto-POST if "always"
  - Otherwise ask consent with three options: "Yes, send now" / "Always send" / "Skip"
  - POST to {KB_HOST}/api/feedback on approval
Do not add closing text after the consent prompt — it is the final UI.
```

Original hook implementation details (for parity):
- Trigger matcher: `startup|clear|compact` (fires on session start, /clear, and context compaction).
- SESSION_ID generation fallback chain: `python3 -c "import uuid; print(uuid.uuid4())"` →
  `uuidgen` → `cat /proc/sys/kernel/random/uuid` → `date +%s%N`.

---

## 4. KB Server — runtime REST API (the one the agent actually calls)

Base URL: `{SW_KB_HOST}` — default `https://sw-plugin.erfouni.ir`.
**All runtime endpoints are public (no auth header).** Content type: JSON.
Field naming on the runtime API is **camelCase**.

### 4.1 Health

```
GET /health           → 200 { "status": "ok" }
```
If unreachable: say "Knowledge base is offline — proceeding without KB lookup" and continue
without KB. **Never abort the user's task because the KB is down.**

### 4.2 Categories

```
GET /api/categories
→ [ { "id": "uuid", "name": "Shaft", "slug": "shaft", "description": "...", "createdAt": "..." }, ... ]
```

### 4.3 Parts (catalog)

```
GET /api/parts?categoryId={uuid}&pageSize=100
GET /api/parts?categoryId={uuid}&q={search}&pageSize=100
GET /api/parts?q={part_number_or_name}&pageSize=20        # free-text fallback
→ {
    "items": [ { "id","partNumber","name","categoryId","description",
                 "material","tags":[...],"status":"active" } ],
    "page": 1, "pageSize": 100, "total": 3
  }
```

```
GET /api/parts/{partId}     # full detail: part + ALL linked published knowledge
→ {
    "id","partNumber","name","categoryId","description","material","tags","status",
    "instructions": [ { "id", "content": "<full markdown build guide>", "partId", "status": "published" } ],
    "macros": [ { "id","name","language":"python|vba|swapi","code":"<full source>",
                  "swFeaturesUsed":["InsertHelix","InsertCutSwept4"],
                  "parameters":{"shaft_diameter_mm":12}, "isTemplate":false, "status":"published" } ],
    "knownErrors": [ { "id","title","description","swFeature","resolution","isResolved","severity" } ],
    "lessons": [ { "id","category","title","whatHappened","rootCause","prevention","severity" } ]
  }
```

### 4.4 Knowledge documents

```
GET /api/knowledge?kind=convention        # ~5 always-apply project conventions
GET /api/knowledge/search?q={task query}  # relevance-ranked docs for the task
GET /api/knowledge/{slug}                 # one doc by slug
→ each doc: { "id", "kind": "reference|convention|playbook|strategy",
              "slug", "title", "category", "severity", "body": "<full markdown>" }
```
Docs may be in **Persian (Farsi) or English** — read both; content is equivalent.

### 4.5 Design rules

```
GET /api/design-rules
→ [ { "ruleCode":"HOLE-001", "category":"fastener|dfm|assembly_clearance|solidworks|tolerance",
      "description":"...", "severity":"low|medium|high|critical",
      "standardReference":"ISO 273", "checkType":"hole_matches_fastener",
      "parameters":{...}, "deprecated": false } ]
```
Skip rules with `deprecated: true`. Severity handling:
critical → block; high → must fix before completing; medium → fix unless user overrides;
low → advisory.

### 4.6 Design-rule checker

```
POST /api/check-context
Content-Type: application/json
Body (all keys optional, additionalProperties allowed — checker skips rules missing inputs):
{
  "welded": true|false,
  "tolerance_class": "f"|"m"|"c"|"v",
  "process": "machined_aluminum"|"welded_steel"|"cast"|...,
  "wall_thickness_mm": number,
  "nominal_dimension_mm": number,
  "fastener": "M8"|"M10"|...,
  "hole_mm": number,
  "material": "Plain Carbon Steel"|"6061-T6"|...
}
→ {
    "results": [ { "ruleCode","category","severity",
                   "status":"pass|fail|warn|advisory|na", "message","description" } ],
    "summary": { "pass":1, "fail":1, "na":2, "advisory":1 }
  }
```
Reaction table: `pass` continue · `fail` **stop and fix the parameter before modeling** ·
`warn` flag to user, fix if possible · `advisory` apply as constraint · `na` ignore.
If `summary.fail > 0` → do not model until resolved.

### 4.7 Standards tables

```
GET /api/standards
→ { "tables": { "fits":16, "tolerances_iso2768":30, "clearance_holes":11, "materials":10,
                "fasteners":13, "sheet_metal_gauges":19, "preferred_numbers":38,
                "surface_finish":9, "gdt_symbols":14, "standard_metadata":8 } }

GET /api/standards/{table}                 # full table
GET /api/standards/{table}/{key}           # one row by key
```
Usage map:
- `materials`, `materials/{name}` — density_g_cm3, yield_mpa, modulus… (mass/stress checks)
- `fits` — ISO 286 rows; filter by hole_basis, shaft_basis, size_min_mm/size_max_mm (µm deviations)
- `clearance_holes`, `clearance_holes/{designation}` — ISO 273: close_mm / normal_mm / loose_mm
  (default `normal_mm` per rule HOLE-001)
- `tolerances_iso2768` — filter by tol_class (f/m/c/v) + range; gives symmetric `tol_mm`
- `fasteners`, `fasteners/{designation}` — pitch_coarse_mm, head_width_mm, head_height_mm, strength_class
- `sheet_metal_gauges` — filter by gauge + material (steel/aluminum/stainless)
- `preferred_numbers` — R5/R10/R20 series check (rule DFM-002)
Query tables **on demand** during design, not all at once.

### 4.8 Global errors & lessons

```
GET /api/errors      # all known SW API errors (check BEFORE calling any SW API method)
GET /api/lessons     # all lessons (apply "prevention" fields as rules)
```

### 4.9 Feedback submission (the write path)

```
POST /api/feedback
Content-Type: application/json
Body: FeedbackSubmission (Section 7)
→ 201 { "id": "feedback_uuid", "state": "pending", ... }
```
- Backend **upserts on `sessionId`** — re-POSTing with the same sessionId updates the record.
- Retry policy: up to 3 attempts, ~2 s apart. 4xx → don't retry (payload malformed), drop
  silently. 5xx/timeout → retry. All fail → drop silently, never bother the user.

---

## 5. Protocol A — `pre-start` (mandatory before any modeling)

Run all phases in order. Do not skip, reorder, or start modeling mid-phase.

**Phase 1 — Conventions.** `GET /api/knowledge?kind=convention`. Load once per conversation.
Treat every convention as a hard rule (units mm/degrees/metric; ISO 2768-mK default tolerance;
default material 6061-T6 unless specified; parametric fully-defined sketches with named dims;
file naming `PRJ-<part>-NNN`, save to `work/`, exports to `exports/`; deliverable = clean
rebuild + material assigned + design-rule check + STEP + drawing PDF). If the user contradicts
a convention, the convention wins unless the user explicitly overrides.

**Phase 2 — Design rules.** `GET /api/design-rules`. Load all, skip `deprecated`, internalize
by category, enforce by severity (see 4.5).

**Phase 3 — Task-relevant docs.** `GET /api/knowledge/search?q={task description}` with a concise
query (e.g. shaft with M8 threads → `q=shaft thread helix swept cut`). Read top 5–8 results
(up to 10 for complex tasks). Priority: playbook → reference → strategy → convention.
**Never skip reference docs for a SW API method you are about to use** — they contain exact
argument counts and failure modes missing from official docs.

**Phase 4 — Initial check-context.** Build the context dict from known parameters and
`POST /api/check-context`. Fix all `fail` results before proceeding (tell the user what failed
and what you changed).

**Phase 5 — Standards lookups on demand** throughout the design (Section 4.7).

**Phase 6 — Post-design validation.** After geometry is complete (before final save/export),
`POST /api/check-context` again with FINAL parameters. Resolve all fails; document advisories
in the session feedback `issues` field.

**Error handling:** server unreachable → log "KB offline — proceeding without pre-start checks"
and continue · 404 on search → proceed with own knowledge · 422 on check-context → retry with
fewer fields, don't block · 5xx → skip phase, note in session issues.
**The KB is an accelerator, not a gatekeeper.**

---

## 6. Protocol B — `kb-api` (catalog lookup, runs after pre-start)

Step 1 — `GET /health`. Offline → announce and build without KB (still do Step 6 if possible).
Step 2 — `GET /api/categories`. Fuzzy-match the user's part to a category → save `categoryId`.
No match → skip to Step 4 fallback.
Step 3 — `GET /api/parts?categoryId={id}&pageSize=100` (optionally `&q=`). Match by
`partNumber` or `name` → save `partId`.
Step 4 — `GET /api/parts/{partId}`; if no partId yet, `GET /api/parts?q={name}&pageSize=20`
then fetch the best match's detail.
Step 5 — Use what was found:
- Part **with** instructions → follow published instructions as the primary build guide; run a
  published non-template macro directly (override `parameters` with user values); read ALL
  `knownErrors` before using any SW feature and apply resolutions proactively; apply lessons as
  rules. Tell the user: "Found existing knowledge for [part]. Using published instructions and
  [N] macros."
- Part **without** instructions → still apply its knownErrors + lessons; build from own
  knowledge. Tell the user it's in the catalog but has no published instructions yet.
- Part **not in KB** → build from scratch; tell the user this session's data will be submitted
  for review.
Step 6 — Always: `GET /api/errors` and `GET /api/lessons` (global). Before every SW API call,
check for a known error on that method; if `isResolved: true`, apply the `resolution` first —
don't trigger the known error.

**Caching:** categories + global errors/lessons once per conversation; part detail once per build.
**Macro usage:** `isTemplate:false` + matching part → run directly (adjust parameters);
`isTemplate:true` → adapt for this part.
**Errors:** 200 use data · 404 build from scratch · 422 log + fallback search · 5xx/timeout skip KB.

---

## 7. Protocol C — `learner` (payload builder)

Active mentally from the first message; when invoked (by session-reporter, or on demand) it
re-reads the ENTIRE conversation and rebuilds a COMPLETE current-state payload (not a delta —
corrected versions only). Can run multiple times.

### 7.1 Steps

1. **Relevance:** if no SolidWorks work happened (no modeling, API calls, code, design decisions,
   error debugging) → return `{ "skip": true, "reason": "no SolidWorks work detected" }` and stop.
2. **Part lookup:** `GET /api/parts?q={part_identifier}` → `partId` (null if none).
   Persist `partId`/`partNumber` in `.sw-learner-state.json`.
3. **Images:** collect from (a) code blocks that save images (`SaveBMP`, `ExportBMP`, `SaveAs`,
   any path ending `.png/.jpg/.jpeg/.bmp/.tiff/.tif/.gif`) and (b) images shown in chat.
   For each existing readable file < 10 MB: base64-encode (`base64 -w 0 file`). On WSL convert
   `C:\foo` → `/mnt/c/foo`. Dedupe by filename. MIME map: png→image/png, jpg/jpeg→image/jpeg,
   bmp→image/bmp, tiff/tif→image/tiff, gif→image/gif.
4. **Build the payload** (schema below) and return it as raw JSON.
5. **Update `.sw-learner-state.json`:**
   `{ "partId", "partNumber", "sessionId", "payloadVersion": <increment from 1>, "lastBuiltAt": "<ISO>" }`

### 7.2 FeedbackSubmission schema (camelCase — match exactly)

```json
{
  "issues":       "string — REQUIRED. 2–5 sentence narrative: what was built, approach, mistakes fixed, final state",
  "sessionId":    "string — the fixed SESSION_ID (mandatory for upsert)",
  "partId":       "uuid or null",
  "images":       [ { "filename": "model.png", "contentType": "image/png", "dataBase64": "<base64>" } ],
  "instructions": [ { "content": "## How to build [part]\n\n**SW version:** ...\n**Material:** ...\n\n### Steps\n1. exact API call + params\n...", "partId": "uuid|null" } ],
  "macros":       [ { "name": "snake_case_name",
                      "description": "one sentence",
                      "language": "python | vba | swapi",
                      "code": "<FULL VERBATIM FINAL SOURCE — complete, never summarized/truncated>",
                      "swFeaturesUsed": ["InsertHelix", "FeatureCut4"],
                      "parameters": { "diameter_mm": 12 },
                      "isTemplate": false,
                      "version": "1.0.0",
                      "partId": "uuid|null" } ],
  "knownErrors":  [ { "title": "short label",
                      "description": "what failed exactly — include return value or error message",
                      "errorCode": "CAD-XXX-001 | null",
                      "swFeature": "SW API method name",
                      "resolution": "exact fix that worked",
                      "isResolved": true,
                      "severity": "low | medium | high | critical" } ],
  "lessons":      [ { "category": "modeling/API | assembly/API | tolerance | fastener | dfm | verification | workflow | session/API",
                      "title": "short rule title",
                      "whatHappened": "narrative",
                      "rootCause": "underlying reason, not the symptom",
                      "prevention": "concrete actionable rule (never 'be careful')",
                      "severity": "low | medium | high | critical",
                      "partId": "uuid|null",
                      "refCode": "CAD-XXX-001 | null",
                      "createsRule": false } ]
}
```

Required/optional: `issues` required; every array key **omitted entirely** when empty (not `[]`).
Macro required fields: `name`, `language`, `code`. KnownError required: `title`, `description`.
Lesson required: `category`, `title`, `whatHappened`, `rootCause`, `prevention`, `severity`.
Lesson optional extras: `ruleCheckType`, `ruleParameters` (used when `createsRule: true`).

### 7.3 Judgment rules

| Include | Skip |
|---|---|
| ALL code blocks written in the session (even tiny snippets) | nothing — all code goes in macros |
| errors with exact failure AND known resolution | vague issues without specifics |
| final working version of each macro | earlier broken versions |
| steps with exact API calls + real parameter values | generic steps anyone knows |
| mistakes that took >1 attempt to fix | immediate typo fixes |
| lessons from successes AND failures demonstrated in THIS session | generic best practices |

When in doubt: **include** — an admin reviews before publishing, and missed knowledge cannot be
recovered after the conversation ends.

Severity mapping for knownErrors: critical = total failure/nothing produced · high = wrong result
that looked correct · medium = caught and fixed quickly · low = minor inconvenience.
Excluded from knownErrors: typos, immediately-fixed syntax errors, issues outside SolidWorks.

---

## 8. Protocol D — `session-reporter` (consent + send)

Runs after the task result is delivered, at end of every session where SolidWorks work happened.

1. **Relevance:** nothing SolidWorks-related happened → stop silently, ask nothing.
2. **Preference check:** `cat ~/.sw-feedback-pref` — if `always` → skip consent, go to POST.
3. **Get the payload** from the learner protocol (Section 7). Learner skipped → stop silently.
4. **Consent prompt** (interactive; in Codex ask as the final message and WAIT for the reply):
   - Question: "Share this session's SolidWorks knowledge with the knowledge base?"
   - Option 1 — **"Yes, send now"**: submit this session's data (pending admin review) → POST.
   - Option 2 — **"Always send"**: POST now AND save preference:
     `echo "always" > ~/.sw-feedback-pref`.
   - Option 3 — **"Skip this session"**: do not POST.
   - Never show the raw JSON payload to the user. Never ask any other question.
5. **POST** `{KB_HOST}/api/feedback` with the payload verbatim (include `sessionId`!).
   Build the request in Python (heredoc) rather than inline curl JSON, so multiline code and
   special characters survive — pattern:

```bash
python3 << 'PYEOF'
import subprocess, json

SESSION_ID = "<SESSION_ID from session context>"
KB_HOST = "https://sw-plugin.erfouni.ir"

payload = { "issues": """...""", "sessionId": SESSION_ID,
            "instructions": [...], "macros": [...],
            "knownErrors": [...], "lessons": [...] }   # + "images" if any

for key in ["instructions", "macros", "knownErrors", "lessons"]:
    if not payload.get(key):
        payload.pop(key, None)

body = json.dumps(payload)
for attempt in range(3):
    r = subprocess.run(["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
                        f"{KB_HOST}/api/feedback",
                        "-H", "Content-Type: application/json", "-d", body],
                       capture_output=True, text=True)
    out = r.stdout.strip().split("\n"); code = out[-1]; resp = "\n".join(out[:-1])
    if code.startswith("2"):
        print(f"Feedback submitted. ID: {json.loads(resp).get('id','?')}"); break
    elif code.startswith("4"):
        print(f"Feedback rejected ({code}): {resp}"); break
    else:
        print(f"Attempt {attempt+1} failed ({code}). Retrying...")
PYEOF
```

6. On success save the returned `id` into `.sw-learner-state.json` as `lastFeedbackId`.
7. Retry ≤3 with ~2 s waits; 4xx → drop immediately and silently; all fail → drop silently.

---

## 9. Backend admin API (reference only — `docs/openapi.json`)

The plugin also ships an OpenAPI 3.0.3 spec for the KB backend's **admin/v1 surface**. The agent
runtime does NOT use it (it uses the public camelCase API of Section 4), but if Codex ever needs
to talk to the authenticated backend, the contract is:

- Servers: `https://<kb-host>/api/v1` · auth: `Bearer` token (`SW_KB_API_KEY`) · field naming **snake_case**.
- Resources & routes:
  - `GET|POST /categories`, `GET|PATCH /categories/{id}` (tree via `parent_id`, `flat` flag)
  - `GET|POST /parts`, `GET|PATCH|DELETE /parts/{id}` (delete = soft, status→deprecated;
    filters: category_id, tags, status, q, page, per_page≤100)
  - `GET|POST /parts/{part_id}/instructions`, `POST .../instructions/bulk`,
    `PUT .../instructions/reorder` ([{id, step_number}]), `PATCH|DELETE /instructions/{id}`
    — instruction = { step_number≥1, title, body (markdown), sw_feature? }
  - `GET|POST /parts/{part_id}/macros`, `GET /macros?language&is_template&q`,
    `GET|PATCH|DELETE /macros/{id}` — macro = { name, language: vba|python|swapi, code,
    description?, sw_features_used[], parameters{}, is_template, version }
  - `GET|POST /parts/{part_id}/errors`, `GET|POST /errors`, `PATCH /errors/{id}`
    — error = { title, description, error_code?, sw_feature?, resolution?, is_resolved, severity }
  - `POST /sessions`, `GET|PATCH /sessions/{id}`, `POST /sessions/{id}/complete`,
    `GET /parts/{part_id}/sessions` — session = { part_id, status: in_progress|completed|failed,
    feature_sequence[], kb_docs_queried[], potential_issues[], iterations_needed?,
    user_rating 1–5?, user_corrections: [{field, original, corrected}] }.
    `/complete` finalizes and auto-records lessons from corrections.
  - `GET|POST /lessons`, `GET /parts/{part_id}/lessons` — lesson = { category, title,
    what_happened, root_cause, prevention, severity, ref_code?, creates_rule,
    rule_check_type?: max_tolerance_class_when|min_value|prefer_series|hole_matches_fastener,
    rule_parameters? }
  - `GET /knowledge/recall?query&k≤20&kinds[]` (semantic search),
    `POST /knowledge/ingest` { source (stable unique id), text, title? } (re-ingest replaces),
    `DELETE /knowledge/{source}`, `POST /knowledge/reindex`
  - `GET /standards/materials[?type]`, `GET /standards/materials/{name}`,
    `GET /standards/fasteners/{designation}?fastener_type`,
    `GET /standards/clearance-holes/{designation}?fit=close|normal|loose`,
    `GET /standards/fits?hole=H7&shaft=g6&nominal=12`,
    `GET /standards/tolerances?class=f|m|c|v&nominal&kind=linear|angular`,
    `GET|POST /standards/design-rules`, `POST /standards/check-context`
  - `GET /health` (no auth)

---

## 10. Files & state the plugin uses on disk

| File | Purpose |
|---|---|
| `~/.sw-feedback-pref` | contains `always` if the user opted into auto-send |
| `.sw-learner-state.json` (cwd) | `{ partId, partNumber, sessionId, payloadVersion, lastBuiltAt, lastFeedbackId }` |
| env `SW_KB_HOST` | KB base URL override (default `https://sw-plugin.erfouni.ir`) |

---

## 11. Build checklist for Codex

1. `AGENTS.md` (global or project) containing Section 3's protocol + a condensed version of
   Sections 5–8 trigger rules ("on any SolidWorks request run pre-start then kb-api; track
   everything; at end run reporter").
2. Four prompt files in `~/.codex/prompts/`: `sw-pre-start.md` (Section 5), `sw-kb-api.md`
   (Section 6), `sw-learner.md` (Section 7), `sw-report.md` (Section 8) — each containing the
   full protocol text so `/sw-pre-start` etc. work standalone.
3. A session-ID convention: on the first SolidWorks request, run `uuidgen` once, echo it into
   the conversation as `SESSION_ID`, and reuse it for every `/api/feedback` POST.
4. All KB calls via `curl` in the shell with double-quoted URLs; feedback POST via the Python
   heredoc pattern (Section 8.5).
5. Honor `~/.sw-feedback-pref` and `.sw-learner-state.json` exactly as specified.
6. Golden rules: KB failures never block the task · consent before sending (unless "always") ·
   payload arrays omitted when empty · `issues` + `sessionId` always present · full verbatim
   code in macros · corrected-versions-only.
