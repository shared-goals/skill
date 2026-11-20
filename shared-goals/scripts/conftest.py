"""Real area integrations are opt-in; never search an operator's skills during collection."""

import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Run tests marked live using local configuration")
    parser.addoption("--boundary-script", metavar="PATH", help="Test one explicitly selected local area script")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires local operator configuration")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(pytest.mark.skip(reason="requires --live"))
