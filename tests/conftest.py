"""Shared fixtures. Tests use an in-memory database and a fixed "today" for repeatable results."""
from datetime import date

import pytest

from data.database import init_db
from data.seed import load_sample

FIXED_TODAY = date(2026, 10, 19)


@pytest.fixture
def today():
    return FIXED_TODAY


@pytest.fixture
def conn():
    connection = init_db(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    load_sample(conn, FIXED_TODAY)
    return conn
