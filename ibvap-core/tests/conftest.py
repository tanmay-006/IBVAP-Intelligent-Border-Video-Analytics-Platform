import pytest
from fastapi.testclient import TestClient

from ibvap_core.api import create_app
from ibvap_core.config import Settings
from ibvap_core.db import make_engine, make_sessionmaker
from ibvap_core.store import EventStore


@pytest.fixture
def settings(tmp_path):
    return Settings(
        site_id="BOP-TEST-01",
        database_url=f"sqlite:///{tmp_path}/ibvap.db",
        mqtt_enabled=False,
        rules_path=str(tmp_path / "no-rules.yaml"),
    )


@pytest.fixture
def store(settings):
    return EventStore(make_sessionmaker(make_engine(settings.database_url)))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c
