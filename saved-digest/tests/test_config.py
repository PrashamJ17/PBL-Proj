"""Configuration resolution from the environment.

Config is read once at startup by an unattended cron job, so a bad value must fail
loudly there rather than producing a surprising batch size five stages later.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from saveddigest.config import GOOGLE_SCOPES, Config


def test_defaults_when_environment_is_empty():
    config = Config.from_env({})
    assert config.youtube_playlist_title == "To Watch"
    assert config.todoist_project_name == "Saved from Instagram"
    assert config.model == "claude-opus-5"
    assert config.effort == "medium"
    assert config.max_searches_per_item == 4
    assert config.digest_item_limit == 12
    assert config.stage_limit == 50
    assert config.anthropic_api_key is None
    assert config.todoist_token is None
    assert config.cookies_from_browser is None


def test_paths_default_under_xdg():
    config = Config.from_env({})
    assert config.config_dir.name == "saved-digest"
    assert config.data_dir.name == "saved-digest"
    # Secrets and data are separate so one can be backed up without the other.
    assert config.config_dir != config.data_dir


def test_explicit_paths_win():
    config = Config.from_env(
        {"SAVED_DIGEST_CONFIG_DIR": "/tmp/cfg", "SAVED_DIGEST_DATA_DIR": "/tmp/dat"}
    )
    assert config.config_dir == Path("/tmp/cfg")
    assert config.data_dir == Path("/tmp/dat")


def test_derived_paths():
    config = Config.from_env(
        {"SAVED_DIGEST_DATA_DIR": "/tmp/dat", "SAVED_DIGEST_CONFIG_DIR": "/tmp/cfg"}
    )
    assert config.db_path == Path("/tmp/dat/saved-digest.db")
    assert config.google_token_path == Path("/tmp/cfg/google_token.json")
    assert config.google_client_secret_path == Path("/tmp/cfg/google_client_secret.json")


def test_overrides_are_read():
    config = Config.from_env(
        {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "TODOIST_API_TOKEN": "tdt",
            "SAVED_DIGEST_TO": "me@example.com",
            "SAVED_DIGEST_MODEL": "claude-sonnet-5",
            "SAVED_DIGEST_EFFORT": "high",
            "SAVED_DIGEST_MAX_SEARCHES": "2",
            "SAVED_DIGEST_ITEM_LIMIT": "5",
            "SAVED_DIGEST_STAGE_LIMIT": "10",
            "SAVED_DIGEST_PLAYLIST_TITLE": "Later",
            "SAVED_DIGEST_PLAYLIST_ID": "PL123",
            "SAVED_DIGEST_TODOIST_PROJECT": "IG",
            "SAVED_DIGEST_COOKIES_BROWSER": "firefox",
        }
    )
    assert config.anthropic_api_key == "sk-ant-test"
    assert config.todoist_token == "tdt"
    assert config.digest_to == "me@example.com"
    assert config.model == "claude-sonnet-5"
    assert config.effort == "high"
    assert config.max_searches_per_item == 2
    assert config.digest_item_limit == 5
    assert config.stage_limit == 10
    assert config.youtube_playlist_title == "Later"
    assert config.youtube_playlist_id == "PL123"
    assert config.todoist_project_name == "IG"
    assert config.cookies_from_browser == "firefox"


@pytest.mark.parametrize(
    "key",
    ["SAVED_DIGEST_MAX_SEARCHES", "SAVED_DIGEST_ITEM_LIMIT", "SAVED_DIGEST_STAGE_LIMIT"],
)
def test_non_numeric_integer_settings_raise(key):
    with pytest.raises(ValueError, match="must be an integer"):
        Config.from_env({key: "lots"})


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_integer_settings_raise(value):
    """A stage limit of 0 would silently process nothing, every run, for ever."""
    with pytest.raises(ValueError, match="must be positive"):
        Config.from_env({"SAVED_DIGEST_STAGE_LIMIT": value})


def test_blank_values_fall_back_to_defaults():
    """`export FOO=` in a sourced .env is common; treat it as unset."""
    config = Config.from_env(
        {
            "ANTHROPIC_API_KEY": "",
            "TODOIST_API_TOKEN": "",
            "SAVED_DIGEST_STAGE_LIMIT": "   ",
            "SAVED_DIGEST_MODEL": "",
        }
    )
    assert config.anthropic_api_key is None
    assert config.todoist_token is None
    assert config.stage_limit == 50
    assert config.model == "claude-opus-5"


def test_ensure_dirs_creates_both_and_restricts_the_secret_dir(tmp_path):
    config = Config.from_env(
        {
            "SAVED_DIGEST_CONFIG_DIR": str(tmp_path / "cfg"),
            "SAVED_DIGEST_DATA_DIR": str(tmp_path / "dat"),
        }
    )
    config.ensure_dirs()
    assert config.config_dir.is_dir()
    assert config.data_dir.is_dir()
    # Holds a long-lived Google refresh token.
    assert oct(config.config_dir.stat().st_mode & 0o777) == "0o700"


def test_ensure_dirs_is_idempotent(tmp_path):
    config = Config.from_env(
        {
            "SAVED_DIGEST_CONFIG_DIR": str(tmp_path / "cfg"),
            "SAVED_DIGEST_DATA_DIR": str(tmp_path / "dat"),
        }
    )
    config.ensure_dirs()
    config.ensure_dirs()
    assert config.config_dir.is_dir()


def test_config_is_frozen():
    """Immutable so a stage cannot mutate settings for later stages."""
    config = Config.from_env({})
    with pytest.raises(FrozenInstanceError):
        config.model = "something-else"  # type: ignore[misc]


def test_google_scopes_cover_both_uses():
    """One consent must grant both the playlist read and the digest send."""
    assert any("youtube.readonly" in s for s in GOOGLE_SCOPES)
    assert any("gmail.send" in s for s in GOOGLE_SCOPES)
    assert len(GOOGLE_SCOPES) == 2
