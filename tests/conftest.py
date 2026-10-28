"""Shared fixtures for Smarter.Homes Update Manager tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ from the repository root."""
    yield
