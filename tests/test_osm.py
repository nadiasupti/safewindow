"""Tests for resilient OpenStreetMap queries."""

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

PIPELINE_PATH = Path(__file__).parents[1] / "pipeline" / "03_osm_roads_places.py"
SPEC = importlib.util.spec_from_file_location("osm_pipeline", PIPELINE_PATH)
osm_pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(osm_pipeline)


def test_retry_osm_call_recovers(monkeypatch):
    calls = 0

    def query():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.exceptions.ConnectionError("temporary outage")
        return "result"

    monkeypatch.setattr(osm_pipeline.time, "sleep", lambda _: None)

    assert osm_pipeline.retry_osm_call(query, attempts=2, delay_seconds=0) == "result"
    assert calls == 2


def test_retry_osm_call_raises_after_attempts(monkeypatch):
    calls = 0

    def query():
        nonlocal calls
        calls += 1
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(osm_pipeline.time, "sleep", lambda _: None)

    with pytest.raises(requests.exceptions.Timeout):
        osm_pipeline.retry_osm_call(query, attempts=3, delay_seconds=0)
    assert calls == 3


def test_main_configures_integer_osm_timeout(monkeypatch):
    class Area:
        def buffer(self, _m):
            return self

        def to_crs(self, _crs):
            return self

        def union_all(self):
            return self

    class Settings:
        overpass_url = "https://example.invalid"
        requests_timeout = None

    class Paths:
        def ensure(self):
            return self

    monkeypatch.setattr(osm_pipeline, "roads", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(osm_pipeline, "villages", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(osm_pipeline, "shelters", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(osm_pipeline, "load_study_area", lambda _paths: Area())
    monkeypatch.setattr(osm_pipeline.config, "get_paths", lambda: Paths())
    monkeypatch.setattr(osm_pipeline.ox, "settings", Settings())
    monkeypatch.setattr(sys, "argv", ["03_osm_roads_places.py", "--osm-timeout", "120"])

    osm_pipeline.main()

    assert osm_pipeline.ox.settings.requests_timeout == 120
