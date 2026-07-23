# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `submit_feedback.py` now sends the payload to curl as UTF-8. It used text-mode
  `subprocess`, which encodes with the locale's code page (cp1252 on most
  Windows machines): characters such as `Ø` or `°` reached the server as invalid
  UTF-8, and characters such as `→` or Persian text crashed the send, which was
  then reported as an unreachable server after a 35-second hang per attempt.
- `validate_feedback.py` and `submit_feedback.py` now read a payload given as
  `-` (stdin) as UTF-8. Text-mode stdin decoded it with the locale's code page,
  so `→` became `â†’` and Persian text was garbled before validation, and the
  garbled text was what got submitted. Reading from a file was not affected.
- The skills, `AGENTS.md` and the runtime API notes now tell the agent to run
  `curl.exe` on Windows. In Windows PowerShell 5.1 `curl` is an alias for
  `Invoke-WebRequest`, so every KB command as written (`curl -sS "..."`)
  failed with "A parameter cannot be found that matches parameter name 'sS'".

### Added

- Added a deterministic installation doctor with human and JSON output for
  Python, bundle integrity, feedback-host configuration, `curl`, and local
  SolidWorks registration.
- Added strict readiness mode, credential-safe diagnostics, runtime tests, and
  a static zero-network boundary check.

## [1.2.0] - 2026-08-02

### Added

- ENG-001, a non-negotiable engineering requirement, as Phase 0 of
  `$sw-pre-start` and at the top of `AGENTS.md`: every component must be a real,
  functional, manufacturable part, modelled separately and justified against
  standards. No schematic, decorative, placeholder or representational geometry;
  when reliable data for a component is unavailable, state what is missing
  rather than inventing values.

  Deliberately duplicated in the plugin rather than left only in the knowledge
  base. The KB carries it as a convention, but this skill is permitted to
  continue through a documented KB outage - which would otherwise be exactly the
  moment the rule disappeared.

## [1.1.0] - 2026-08-02

### Added

- Classification hints on feedback submission: `suggestedCategory`,
  `suggestedPartName` and `suggestedPartNumber`. The agent that built the
  component records what it believes it made, so a reviewer confirms rather
  than deduces it from code and renders. All three are optional and advisory -
  nothing is published on their strength, and the part is still set only by an
  explicit reviewer action.

### Changed

- `docs/openapi.json` regenerated from the running knowledge base. The previous
  copy declared `/api/v1` servers while the API mounts at `/api`, documented a
  bearer token the public API does not require, and omitted the feedback
  endpoint entirely.

### Fixed

- The submission schema set `additionalProperties: false`, so any field added
  to the API would have been rejected locally before reaching the server. The
  three hint fields are now declared.

## [1.0.2] - 2026-07-20

### Fixed

- Made the bundled validator work in Codex's versioned plugin-cache layout as
  well as in a source checkout.
- Added a Python 3.9/3.13 CI gate that installs the bundle into a temporary
  versioned layout and runs its complete structural and runtime checks there.

## [1.0.1] - 2026-07-20

### Added

- Root install manifest for direct plugin discovery.
- Project and bundled plugin icons.
- Security disclosure policies, bundled license, and package-level README.
- HOL Plugin Scanner CI with an 80-point minimum score and high-severity gate.
- Repository checks for manifest consistency, icon integrity, package documents,
  and immutable GitHub Action references.

### Changed

- Pinned all external GitHub Actions to full commit SHAs.
- Expanded the public README with the validated workflow, trust boundaries, and
  a concrete first-task example.
- Added contribution guidance, structured issue forms, and repository social
  preview artwork.

## [1.0.0] - 2026-07-20

### Added

- Initial public release with five coordinated SolidWorks design, knowledge,
  learning, and reporting skills.
- Deterministic session, feedback validation, and submission utilities.
- Plugin marketplace metadata, MIT license, and upstream attribution.

[Unreleased]: https://github.com/Erfouni/solidworks-GPT-plugin/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/Erfouni/solidworks-GPT-plugin/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/Erfouni/solidworks-GPT-plugin/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Erfouni/solidworks-GPT-plugin/releases/tag/v1.0.0
