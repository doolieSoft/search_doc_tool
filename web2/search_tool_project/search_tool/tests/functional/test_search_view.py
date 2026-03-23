"""Functional tests for SearchView (POST /search/)."""
import os

import pytest
from django.contrib.auth.models import User
from django.test import Client

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
SAMPLE_PDF = os.path.join(FIXTURES_DIR, "sample.pdf")
FIXTURES_PARENT = os.path.dirname(SAMPLE_PDF)


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username="testuser", password="pass")
    return c


@pytest.mark.django_db
class TestSearchView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.post("/search/", {"folder": FIXTURES_PARENT, "terms": "test"})
        assert response.status_code == 302

    def test_invalid_folder_returns_error(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": "/nonexistent/folder/xyz",
            "terms": "test",
        })
        assert response.status_code == 200
        assert b"Dossier invalide" in response.content

    def test_empty_terms_returns_error(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": FIXTURES_PARENT,
            "terms": "",
        })
        assert response.status_code == 200
        assert b"Entrez au moins un terme" in response.content

    def test_too_short_term_returns_error(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": FIXTURES_PARENT,
            "terms": "ab",
        })
        assert response.status_code == 200
        assert b"3 caract" in response.content

    def test_valid_search_returns_results_partial(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": FIXTURES_PARENT,
            "terms": "FIXTURE_TERM_ONE",
        })
        assert response.status_code == 200
        assert b"FIXTURE_TERM_ONE" in response.content

    def test_uses_results_partial_template(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": FIXTURES_PARENT,
            "terms": "FIXTURE_TERM_ONE",
        })
        assert "search_tool/_results.html" in [t.name for t in response.templates]

    def test_no_match_returns_empty_results(self, client_logged_in):
        response = client_logged_in.post("/search/", {
            "folder": FIXTURES_PARENT,
            "terms": "ZZZZ_NONEXISTENT_ZZZ",
        })
        assert response.status_code == 200
        # Should render without error, just no results
