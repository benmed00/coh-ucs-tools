"""Pytest hooks shared by unittest-style API tests."""

from __future__ import annotations

import os

import pytest

_AUTH_ENV_KEYS = (
    "UCS_API_KEY",
    "UCS_ADMIN_PASSWORD",
    "UCS_OAUTH_CLIENT_ID",
    "UCS_OAUTH_CLIENT_SECRET",
    "UCS_SESSION_SECRET",
    "UCS_REQUIRE_AUTH_ALL",
)


@pytest.fixture(scope="session", autouse=True)
def _clear_stale_webapp_auth_env():
    """Drop auth env vars leaked from the developer shell before any tests import the app."""
    for key in _AUTH_ENV_KEYS:
        os.environ.pop(key, None)
