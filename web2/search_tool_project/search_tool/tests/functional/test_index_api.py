"""Functional tests for index API views (start/stop/status/summary/unindexed)."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
FIXTURES_PARENT = os.path.dirname(os.path.join(FIXTURES_DIR, "sample.pdf"))


@pytest.fixture(autouse=True)
def reset_index_state():
    """Reset the global _index_state to avoid state leakage between tests."""
    import search_tool.indexing_state as idx_state
    idx_state._index_state["running"] = False
    idx_state._index_state["error"] = None
    yield
    idx_state._index_state["running"] = False
    idx_state._index_state["error"] = None


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username="testuser", password="pass")
    return c


@pytest.mark.django_db
class TestIndexStatusView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.get("/index/status/")
        assert response.status_code == 302

    def test_returns_json(self, client_logged_in):
        response = client_logged_in.get("/index/status/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "running" in data
        assert "done" in data
        assert "total" in data

    def test_running_is_false_initially(self, client_logged_in):
        response = client_logged_in.get("/index/status/")
        data = json.loads(response.content)
        assert data["running"] is False


@pytest.mark.django_db
class TestStartIndexView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.post("/index/start/", {"folder": FIXTURES_PARENT})
        assert response.status_code == 302

    def test_invalid_folder_returns_400(self, client_logged_in):
        response = client_logged_in.post("/index/start/", {"folder": "/nonexistent/xyz"})
        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data

    def test_valid_folder_starts_indexing(self, client_logged_in):
        mock_thread = MagicMock()
        with patch("search_tool.views.post.start_index.threading.Thread",
                   return_value=mock_thread) as mock_thread_cls:
            response = client_logged_in.post("/index/start/", {
                "folder": FIXTURES_PARENT,
                "recurse": "true",
            })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data.get("started") is True
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()


@pytest.mark.django_db
class TestStopIndexView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.post("/index/stop/")
        assert response.status_code == 302

    def test_stop_returns_json(self, client_logged_in):
        response = client_logged_in.post("/index/stop/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data.get("stopped") is True


@pytest.mark.django_db
class TestIndexSummaryView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.get("/index/summary/", {"folder": FIXTURES_PARENT})
        assert response.status_code == 302

    def test_invalid_folder_returns_zeros(self, client_logged_in):
        response = client_logged_in.get("/index/summary/", {"folder": "/nonexistent/xyz"})
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == {"total": 0, "indexed": 0}

    def test_valid_folder_returns_counts(self, client_logged_in):
        response = client_logged_in.get("/index/summary/", {
            "folder": FIXTURES_PARENT,
            "recurse": "true",
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "total" in data
        assert "indexed" in data
        assert isinstance(data["total"], int)


@pytest.mark.django_db
class TestIndexUnindexedView:
    def test_invalid_folder_returns_empty(self, client_logged_in):
        response = client_logged_in.get("/index/unindexed/", {"folder": "/nonexistent/xyz"})
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == {"files": []}

    def test_valid_folder_returns_files_and_paths(self, client_logged_in):
        response = client_logged_in.get("/index/unindexed/", {
            "folder": FIXTURES_PARENT,
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "files" in data
        assert "paths" in data
