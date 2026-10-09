import pandas as pd

from app.streamlit_app import is_default_data_dir, route_for_date
from safewindow import config


def test_is_default_data_dir_uses_environment_selection(monkeypatch):
    paths = config.get_paths()

    monkeypatch.delenv("SAFEWINDOW_DATA_DIR", raising=False)
    assert is_default_data_dir(paths)

    monkeypatch.setenv("SAFEWINDOW_DATA_DIR", "data_demo")
    assert not is_default_data_dir(paths)


def test_route_for_date_uses_only_routes_available_on_or_before_selection():
    routes = pd.DataFrame({
        "village_id": ["v1", "v1"],
        "date": pd.to_datetime(["2022-06-07", "2022-06-14"]),
        "shelter_id": ["s1", "s2"],
        "shelter_name": ["Shelter 1", "Shelter 2"],
        "length_m": [1000, 2000],
    })

    selected = route_for_date(routes, "v1", pd.Timestamp("2022-06-10"))

    assert len(selected) == 1
    assert selected.iloc[0]["shelter_id"] == "s1"
    assert selected.iloc[0]["length_m"] == 1000
