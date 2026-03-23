"""Unit tests for ConfigService."""
import json
import os
import tempfile

import pytest

from search_tool.services.config_service import ConfigService, remove_accents


class TestRemoveAccents:
    def test_basic_accents(self):
        assert remove_accents("éàü") == "eau"

    def test_cafe(self):
        assert remove_accents("café") == "cafe"

    def test_resume(self):
        assert remove_accents("résumé") == "resume"

    def test_curly_quotes_normalized(self):
        # U+2018 and U+2019 → apostrophe
        assert remove_accents("\u2018hello\u2019") == "'hello'"

    def test_modifier_letter_apostrophe(self):
        assert remove_accents("\u02bcword") == "'word"

    def test_non_breaking_space(self):
        assert remove_accents("hello\u00a0world") == "hello world"

    def test_narrow_no_break_space(self):
        assert remove_accents("hello\u202fworld") == "hello world"

    def test_plain_ascii_unchanged(self):
        assert remove_accents("hello world 123") == "hello world 123"

    def test_empty_string(self):
        assert remove_accents("") == ""


class TestConfigService:
    @pytest.fixture
    def tmp_cfg(self, tmp_path):
        return str(tmp_path / "config.json")

    def test_load_missing_file_returns_empty(self, tmp_cfg):
        svc = ConfigService(config_file=tmp_cfg)
        assert svc.load() == {}

    def test_save_and_load(self, tmp_cfg):
        svc = ConfigService(config_file=tmp_cfg)
        svc.save({"folder": "/some/path", "recurse": True})
        loaded = svc.load()
        assert loaded["folder"] == "/some/path"
        assert loaded["recurse"] is True

    def test_load_corrupted_file_returns_empty(self, tmp_cfg):
        with open(tmp_cfg, "w") as f:
            f.write("not valid json {{{")
        svc = ConfigService(config_file=tmp_cfg)
        assert svc.load() == {}

    def test_save_does_not_raise_on_unwritable(self, tmp_path):
        # Save to a path under a read-only directory
        svc = ConfigService(config_file=str(tmp_path / "nonexistent_subdir" / "cfg.json"))
        # Should silently fail, not raise
        svc.save({"key": "value"})

    def test_load_favorites_empty(self, tmp_cfg):
        svc = ConfigService(config_file=tmp_cfg)
        assert svc.load_favorites() == []

    def test_save_and_load_favorites(self, tmp_cfg):
        svc = ConfigService(config_file=tmp_cfg)
        svc.save_favorites(["/a/path", "/b/path"])
        assert svc.load_favorites() == ["/a/path", "/b/path"]

    def test_save_favorites_preserves_other_keys(self, tmp_cfg):
        svc = ConfigService(config_file=tmp_cfg)
        svc.save({"recurse": False, "folder": "/x"})
        svc.save_favorites(["/fav"])
        cfg = svc.load()
        assert cfg["recurse"] is False
        assert cfg["favorites"] == ["/fav"]

    def test_remove_accents_static_method(self):
        assert ConfigService.remove_accents("été") == "ete"
