# Code health

Audits and remediation tracking for LogFlare Backend code quality, security, and technical debt.

## Layout

- `history/` — one markdown snapshot per audit (or remediation wave)
- Filename rule: `YYYY-MM-DD-<slug>.md`
- Finding / action ID rule: `CH-YYYY-MM-DD-NN`

## Usage

1. Run a Plan-mode audit (see codebase-health-audit skill).
2. Write findings and planned actions under `history/`.
3. After Agent-mode fixes, update that file’s `## Remediation log`.
