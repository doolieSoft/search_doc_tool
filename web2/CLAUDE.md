# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

This is a **refactoring** of the Django application located in `../web/`.
The goal is to restructure the codebase while keeping **all existing functionality intact**.

Reference implementation: `../web/search_tool_project/`
Target: `web2/search_tool_project/`

---

## Non-negotiable rules

- **Zero functional regression**: every feature present in `../web/` must work identically.
- **All URLs, JSON response shapes, and template variable names must remain identical** to the original — the frontend (HTML/JS) is not refactored.
- **Do not simplify or remove features** to make the code easier to write.

---

## Project structure

```
web2/
  search_tool_project/
    manage.py
    project/              Django settings (DJANGO_SETTINGS_MODULE=project.settings)
    search_tool/          Django app
      views/
        get/              One file per GET view
        post/             One file per POST view
        __init__.py       Re-exports all views for urls.py
      services/           Business logic as Python classes
      models.py
      urls.py
      templates/
      static/
      tests/
        unit/             Unit tests for services
        functional/       Integration/view tests
        fixtures/         Test files (PDF, DOCX)
```

---

## Views

### Rules

- Every view **must** inherit from `django.views.View` and `django.contrib.auth.mixins.LoginRequiredMixin`.
- GET views go in `views/get/`, POST views go in `views/post/`.
- A view that handles both GET and POST goes in the folder matching its primary method; document the secondary method clearly.
- One class per file. The class name matches the file name in PascalCase (e.g. `views/get/index.py` → `IndexView`).
- `views/__init__.py` re-exports everything so `urls.py` can import cleanly.
- Superuser-only views must additionally check `request.user.is_superuser` and return 403 if not met — do **not** use a separate decorator, do it inside the method.

### Example

```python
# views/get/index.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.shortcuts import render


class IndexView(LoginRequiredMixin, View):
    def get(self, request):
        ...
        return render(request, "search_tool/index.html", context)
```

```python
# views/__init__.py
from .get.index import IndexView
from .get.search import SearchView
from .post.index_start import IndexStartView
# etc.
```

```python
# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    ...
]
```

---

## Services

### Rules

- All business logic lives in `services/`. No logic in views beyond request parsing and response building.
- Each service is a **Python class** with explicit `__init__` dependencies (no global state, no module-level singletons).
- Services receive their dependencies (db_file, cache_dir, etc.) via constructor — do not read `settings` inside a service method.
- Views instantiate services using values from `django.conf.settings`.
- Class methods must have explicit type hints on parameters and return values.

### Service mapping (from original functions)

| Original module | New class |
|---|---|
| `services/search.py` | `SearchService` |
| `services/index.py` | `IndexService` |
| `services/converter.py` | `ConverterService` |
| `services/extractor.py` | `ExtractorService` |
| `services/config.py` | `ConfigService` |

### Example

```python
# services/index_service.py
class IndexService:
    def __init__(self, db_file: str):
        self.db_file = db_file

    def is_indexed(self, path: str) -> bool:
        ...

    def index_file(self, path: str, pdf_cache_dir: str) -> bool:
        ...

    def fts_search(self, terms: list[str], mode: str, case_sensitive: bool) -> list[dict]:
        ...
```

---

## Tests

### Rules

- Tests are **mandatory** for all services and views.
- Use `pytest` with `pytest-django`.
- Use `pytest` fixtures, not `unittest.TestCase` (except where Django `TestCase` is needed for DB isolation).
- Each test file mirrors the source file it tests (e.g. `services/index_service.py` → `tests/unit/test_index_service.py`).

### Unit tests (`tests/unit/`)

- Test service classes in isolation.
- Mock filesystem calls and DB when testing logic; use a real in-memory SQLite for index tests.
- Cover: normal cases, edge cases, error cases.

### Functional tests (`tests/functional/`)

- Test views via Django's `Client` or `RequestFactory`.
- Test the full request/response cycle including authentication.
- Use the test fixtures in `tests/fixtures/`.

### Test fixtures (`tests/fixtures/`)

- Provide at least:
  - `sample.pdf` — a real multi-page PDF with known text content
  - `sample.docx` — a real DOCX with known text content
  - `sample_encrypted.docx` — a password-protected DOCX (to test the skip logic)
- Tests must assert on specific text found in these fixture files — do not use mocks for content.

### Running tests

```bash
cd web2/search_tool_project
pytest
pytest tests/unit/                    # unit only
pytest tests/functional/              # functional only
pytest -k test_index_service          # single test file
```

### Configuration

`pytest.ini` or `pyproject.toml` must define:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = project.settings
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

---

## Refactoring order

Follow this order to avoid breaking dependencies:

1. Set up project scaffold (copy settings, models, migrations, templates, static as-is)
2. Refactor `services/` into classes (no view changes yet — keep original views temporarily)
3. Write unit tests for all services and make them pass
4. Refactor views into `views/get/` and `views/post/` structure
5. Write functional tests for all views
6. Remove original views
7. Final check: run all tests, manually verify all features

---

## What must NOT change

- `models.py` — model definitions, field names, migrations
- `templates/` — all templates, unchanged
- `static/` — all static files, unchanged
- URL names — `name=` in `urlpatterns` must be identical
- JSON response shapes — keys and value types must be identical to original
- `~/.search_tool_config.json` format — shared with the desktop app
- Per-folder data layout: `.data/folders/<name>_<hash>/`
