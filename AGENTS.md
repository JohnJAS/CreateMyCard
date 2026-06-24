# Repository Guidelines

## Project Structure & Module Organization

This repository contains tooling for generating and validating HarmonyOS A2UI card DSL. The active Python CLI and libraries live under `test/`: `batch_generate.py` is the batch entrypoint, `createmycard_generator/` contains prompt/config/pipeline code, and `createmycard_validator/` contains the static DSL validator, profiles, and rule metadata. Generation guidance and reference material live in `skills/harmony-card-generation/`. Reusable visual and layout examples are in `template/scene/` and `template/layout/`. Keep generated outputs in ignored output folders, not in source directories.

## Build, Test, and Development Commands

Install runtime dependencies before using the generator:

```powershell
pip install requests python-dotenv
```

Run a configuration-only check without calling the API:

```powershell
python test/batch_generate.py --dry-run --validate --max-retry 1 --no-extract-keywords
```

Validate rule/profile metadata:

```powershell
python test/createmycard_validator/validate_rules.py
```

Compile-check Python files:

```powershell
python -m compileall -q test
```

Validate a generated `.dat` file:

```powershell
python test/createmycard_validator/validator.py output/q1.dat --profile train
```

## Coding Style & Naming Conventions

Use Python 3 style with 4-space indentation, type hints where they clarify interfaces, and small modules with focused responsibilities. Keep validator rules named by module and number, such as `RULE_DESIGN_009`, and store matching metadata in `test/createmycard_validator/rules/*_rules.json`. Prefer existing helpers in `common.py`, `engine.py`, and `registry.py` over duplicating traversal or rule-loading logic.

## Testing Guidelines

There is no checked-in pytest suite yet; validation scripts are the primary safety net. For validator changes, update the relevant `rules/*.json`, profile files, and module validator together, then run `validate_rules.py` plus at least one sample DSL validation. For generator changes, run the dry-run command and avoid network/API calls unless explicitly needed.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `update repo structure` and `Add test folder with card generator and validator`. Follow that style: describe the concrete change in one line. Pull requests should include a brief purpose statement, commands run, affected DSL/rule areas, and screenshots or sample outputs when templates or generated card visuals change.

## Security & Configuration Tips

Do not commit `.env`, `.env.*`, `.claude/`, `.agents/`, tokens, or generated local caches. Configure API access with environment variables or local settings only, including `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_MODEL`.
