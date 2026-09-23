"""Shared pytest fixtures."""

import pytest
from moto import mock_aws


@pytest.fixture
def aws(monkeypatch):
    """Mocked AWS with fake credentials so no real account is touched."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield
