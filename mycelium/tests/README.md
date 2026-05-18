# tests/

Unit and integration tests for the Mycelium backend.

Run from the project root (`mycelium/mycelium/`):

```
cd mycelium/mycelium
```

---

## test_unit.py — no external connections required

```
pytest tests/test_unit.py -v
```

Tests that run without MongoDB, GitLab, or Vertex AI. Safe to run anywhere,
no `.env` needed.

| Test class | What it covers |
|------------|---------------|
| `TestDeveloperNode` | Pydantic model defaults and field behaviour (external flag, expertise dict) |
| `TestContributionEdge` | Edge model: expertise score, external flag, CODEOWNERS vs commit vs MR approver scoring |
| `TestBusFactor` | `compute_bus_factor()` — 80% coverage threshold, single contributor, even split, dominant contributor |
| `TestFindingModel` | Finding schema, auto-generated UUID, evidence/actions defaults; confirms `ModuleNode` has no score fields |
| `TestCodeownersParser` | `get_codeowners()` parsing logic: comments, blank lines, multi-owner, `@` stripping |
| `TestExternalContributorClassification` | `get_commit_contributors()` internal/external logic: name matching, deduplication |
| `TestTryParseJson` | `try_parse_json()` robustness: clean JSON, markdown fences, prose prefix, nested objects |

---

## test_integration.py — requires live MongoDB

```
pytest tests/test_integration.py -v
```

Uses an isolated `mycelium_test` database — **safe to run, will not touch
production data**. All collections are dropped and re-created before each test.

Requires `MONGODB_URI` in `.env`.

| Test class | What it covers |
|------------|---------------|
| `TestDeveloperSeparation` | Internal vs external developer storage and retrieval; `list_developers(active_only)` and `list_upstream_authors()` |
| `TestSnapshot` | `snapshot()` returns expected keys; upstream authors appear in the right bucket; internal and external are cleanly separated |
| `TestContributions` | `upsert_contribution()` idempotency and score overwrite; CODEOWNERS vs MR approver scores; external flag; contributor sort order |
| `TestModuleConcentration` | `list_concentrated_modules()` inclusion/exclusion; `get_module()` returns declared owners |

---

## conftest.py

Adds the project root to `sys.path` so all imports work when running pytest
from the `mycelium/mycelium/` directory.

---

## pytest.ini

Configures pytest for async tests:

```ini
asyncio_mode = auto
```

---

## Prerequisites

Unit tests:
```
pip install -r requirements.txt
pytest tests/test_unit.py -v
```

Integration tests (additionally):
```
MONGODB_URI=mongodb+srv://... pytest tests/test_integration.py -v
```
