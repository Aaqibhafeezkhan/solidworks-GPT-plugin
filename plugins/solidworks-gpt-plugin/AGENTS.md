# SolidWorks GPT Plugin protocol

Apply these rules to every SolidWorks request handled with this plugin.

## ENG-001: real parts only

Every component must be a real, functional, manufacturable, technically accurate
part. Never produce schematic, decorative, conceptual, simplified, placeholder,
or visually representative geometry - at any size or level of importance.

Research each component against standards and manufacturer data, justify every
dimension, and model every physical part separately: a 10,000-part assembly is
10,000 engineered parts, never a simplified block or visual shell standing in
for a group.

When reliable information for a component is unavailable, **say what is missing
and stop** - do not fabricate values. A plausible-looking part built from
invented numbers looks finished and will be trusted, which makes it worse than
no part at all.

This holds regardless of KB availability. `$sw-pre-start` Phase 0 carries the
full requirement.

## Session identity

On the first SolidWorks request in a Codex task, run `scripts/sw_session.py
start` once. Keep the returned UUID as `SESSION_ID` for the rest of the task.
Never regenerate it mid-task. Include it as `sessionId` in every feedback POST.

Use `SW_KB_HOST` when set; otherwise use `https://sw-plugin.erfouni.ir`.

## Mandatory order

1. Establish the goal, units, geometry-driving dimensions, material,
   tolerances, and required outputs. Ask when missing information affects
   geometry or safety; do not invent engineering values.
2. Use `$sw-pre-start` before opening SolidWorks, generating CAD code, or
   making a SolidWorks API call.
3. Use `$sw-kb-api` immediately after pre-start.
4. Plan features, sketches, datums, relations, and measurable acceptance
   criteria before changing the model.
5. Query standards for material, fit, tolerance, fastener, and clearance data
   when those decisions arise.
6. Build and validate each part separately. Check rebuild status, errors,
   feature tree, mass, bounding box, and an image; save and close the part
   before creating an assembly.
7. For assemblies, verify mates and remaining degrees of freedom.
8. Treat deterministic document validation as pass/fail; screenshots are only
   visual evidence.
9. Export the requested deliverables and report measured values, errors, and
   limitations explicitly.
10. Track exact final instructions, all final code, reproducible errors and
    fixes, and non-obvious lessons throughout the task.
11. After delivering the CAD result, use `$sw-session-reporter`.

## Knowledge-base transport

Use `curl` through the shell for every KB request. Do not use browser or
web-fetch tools for KB runtime calls. Quote every URL. Runtime endpoints are
public and use camelCase JSON. KB failure is never a reason to abandon the CAD
task; record it and continue.

On Windows, run `curl.exe` instead of `curl`: in Windows PowerShell 5.1
`curl` is an alias for `Invoke-WebRequest`, which rejects curl options such
as `-sS`. `curl.exe` is the real curl in every Windows shell.

Do not submit session feedback without explicit consent unless
`~/.sw-feedback-pref` contains exactly `always`.
