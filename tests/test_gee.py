"""Tests for Earth Engine export handling."""

import urllib.error

from safewindow.flood import Grid
from safewindow.gee import chunk_bounds, raster_window, retry_ee_download


def test_retry_ee_download_recovers(monkeypatch):
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"tiff"

    def urlopen(url):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(url, 400, "temporary export rejection", None, None)
        return Response()

    monkeypatch.setattr("safewindow.gee.urllib.request.urlopen", urlopen)
    monkeypatch.setattr("safewindow.gee.time.sleep", lambda _: None)

    assert retry_ee_download("https://example.invalid/tile", attempts=2, delay_seconds=0) == b"tiff"
    assert calls == 2


def test_chunk_bounds_cover_grid_without_overlaps():
    grid = Grid(xmin=0, ymax=100, width=10, height=10, res=10)

    chunks = list(chunk_bounds(grid, tile_width=4, tile_height=4))

    assert chunks == [
        (0, 0, 4, 4), (4, 0, 8, 4), (8, 0, 10, 4),
        (0, 4, 4, 8), (4, 4, 8, 8), (8, 4, 10, 8),
        (0, 8, 4, 10), (4, 8, 8, 10), (8, 8, 10, 10),
    ]


def test_chunk_bounds_rejects_non_positive_tile_size():
    grid = Grid(xmin=0, ymax=100, width=10, height=10, res=10)

    try:
        list(chunk_bounds(grid, tile_width=0))
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_raster_window_uses_width_and_height():
    window = raster_window((1600, 0, 2400, 800))
    assert window.width == 800
    assert window.height == 800
    assert window.col_off == 1600
    assert window.row_off == 0
