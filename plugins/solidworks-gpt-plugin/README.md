# SolidWorks GPT Plugin

This is the installable plugin bundle from
[`Erfouni/solidworks-GPT-plugin`](https://github.com/Erfouni/solidworks-GPT-plugin).
It gives Codex five coordinated skills for requirements capture, engineering
knowledge lookup, SolidWorks planning and validation, session learning, and
consent-based reporting.

## Included skills

- `solidworks-design` orchestrates the complete design workflow.
- `sw-pre-start` loads conventions, rules, and task-relevant knowledge.
- `sw-kb-api` retrieves published instructions, macros, errors, and lessons.
- `sw-learner` builds a corrected session feedback payload.
- `sw-session-reporter` obtains consent and optionally submits feedback.

The plugin does not bundle SolidWorks or an automation server. Actual CAD work
requires an existing SolidWorks installation and a compatible Codex automation
surface. Knowledge-base outages do not block local modeling.

## Diagnose local readiness

From this installed bundle, run:

```powershell
python scripts/doctor.py
```

The doctor checks Python, bundle integrity, `SW_KB_HOST` syntax, `curl`, and
SolidWorks COM registration without making a network request or launching
SolidWorks. Use `--strict` to require both external applications and `--json`
for machine-readable evidence.

## Privacy

Feedback stays local unless the user chooses **Yes, send now** or has explicitly
saved the **Always send** preference. Review generated macros, models, and
exports before production use. See [SECURITY.md](SECURITY.md) for reporting and
trust boundaries.

For installation, examples, validation commands, and contribution guidance,
read the [repository documentation](https://github.com/Erfouni/solidworks-GPT-plugin#readme).
