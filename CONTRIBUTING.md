# Contributing

Thanks for helping improve the SolidWorks GPT Plugin. Contributions should
make the CAD workflow safer, more reproducible, easier to validate, or easier
to understand.

## Development setup

1. Fork or clone the repository.
2. Create a focused branch from `main`.
3. Use Python 3.9 or newer.
4. Run the complete local check suite:

   ```powershell
   python plugins/solidworks-gpt-plugin/scripts/run_checks.py
   ```

The checks validate the plugin manifest, marketplace entry, skill structure,
feedback schema, Python syntax, runtime tests, and the installation doctor's
zero-network import boundary. Pull requests run the same suite on Python 3.9
and 3.13.

## Where changes belong

| Area | Path |
|---|---|
| Plugin manifest | `plugins/solidworks-gpt-plugin/.codex-plugin/plugin.json` |
| Agent protocol | `plugins/solidworks-gpt-plugin/AGENTS.md` |
| Skills | `plugins/solidworks-gpt-plugin/skills/` |
| Runtime helpers | `plugins/solidworks-gpt-plugin/scripts/` |
| Tests | `plugins/solidworks-gpt-plugin/tests/` |
| Schemas and API references | `plugins/solidworks-gpt-plugin/schemas/` and `docs/` |

## Pull request checklist

- Keep the change focused and explain the user or developer impact.
- Add or update tests for runtime behavior.
- Preserve the mandatory pre-start, knowledge lookup, validation, and
  consent-based reporting sequence.
- Never include API keys, tokens, private CAD files, customer data, or local
  learner-state files.
- Do not weaken feedback consent or send feedback during tests.
- Run `run_checks.py` and include the result in the pull request description.

## Reporting bugs

Use the bug-report form and provide the smallest reproducible example you can.
Redact credentials, proprietary model data, machine identifiers, and private
knowledge-base content from logs and screenshots.

Security-sensitive reports should not include exploit details in a public
issue. Open a minimal issue asking for a private contact path instead.
