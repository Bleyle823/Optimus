# Optimus-2 / Hotel RaaS commit conventions

## Conventional Commit scopes
Use when helpful: `docs`, `webots`, `escrow`, `hotel`, `config`, `tests`, `chore`, `settlement`, `cursor`.

## Pre-commit verification (fast path)
From repo root:

```bash
python -m pip install -r requirements.txt
python -m unittest tests.test_hotel -v
```

Optional when Rust is available:

```bash
cd contracts/task_escrow && cargo test
```

## Never stage
- `keys/` and any `*.json` key material
- `.env` (only `.env.example` is tracked)
- `settlement/outbox.json`
- `settlement/receipts/*.json` (except `.gitkeep`)
- `**/__pycache__/`, `*.pyc`
- `hotel_raas_local.json`
- `.cursor/plans/`

## Hackathon disclosure
The Webots kitchen world is baseline (pre-window). The NEAR task escrow, `hotel/` dispatcher, and settlement docs are hackathon-window work. Mention that split in commit bodies when touching README or HACKATHON.md (see HACKATHON.md Q-002/Q-003).

## Branch flow
Feature branch → `develop` → `main`. Push `origin/develop` and `origin/main` after review.
