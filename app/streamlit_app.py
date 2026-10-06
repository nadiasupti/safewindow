"""SafeWindow - Streamlit app (Step 8).

    streamlit run app/streamlit_app.py
    (set SAFEWINDOW_DATA_DIR=data_demo to view the synthetic demo)

Reads only the pre-computed files in <data>/app/ (pipeline/08_build_app_data.py),
so it stays fast and does not need the heavy GIS libraries.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import altair as alt
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import config  # noqa: E402

STATUS_COLOR = {"connected": "#2e9d4f", "isolated": "#d7263d", "uncertain": "#f39c12",
                "boat_dependent": "#8a8f98"}

T = {
    "en": {
        "title": "SafeWindow", "tagline": "When does each village lose its last road to a flood shelter?",
        "language": "Language", "supply": "Household supply days (assumption)",
        "supply_help": "Days of food and water a family has on hand once cut off. This is an assumption, not a measurement.",
        "date": "Date", "showing": "Map shows the flood observed on {d} ({src}).",
        "no_obs": "No observation on or before this date - showing the first one ({d}).",
        "unknown_note": "{p}% of the area had no usable image (cloud / no coverage) - shown in grey.",
        "connected": "connected to a shelter", "isolated": "isolated (no road to any shelter)",
        "uncertain": "uncertain (roads under cloud)", "boat_dependent": "boat-dependent (> 500 m from a road)",
        "urgent": "Responder view - most urgent villages", "rank": "#", "village": "Village",
        "pop": "Population", "isolated_when": "Isolated", "deadline": "Aid deadline",
        "pick": "Select a village (or click one on the map)", "none": "-",
        "panel": "Village details", "isolation": "Isolation date",
        "never": "Not isolated on any observed date", "safe_exit": "Last safe exit",
        "route": "{km:.1f} km by road to {s}", "no_exit": "No safe exit observed (already cut off on the first image)",
        "deadline_label": "Aid deadline (Survival Clock)", "days_left": "{n} days of supplies left on {d}",
        "deadline_passed": "Supplies ran out {n} days before {d}", "not_yet": "Not isolated yet on {d}",
        "sms": "SMS preview (Bangla)", "rain": "Daily rainfall - NASA GPM IMERG",
        "modis": "Flooded area - NASA MODIS daily flood product", "upstream": "Meghalaya hills (upstream)",
        "local": "Sunamganj", "sens": "Sensitivity test (road cut cutoff)", "valid": "Validation against news reports",
        "limits": "Limits of this prototype",
        "limits_text": ("- Supply days is an assumption, not measured.\n"
                        "- Flood maps have gaps from clouds and radar errors; dates between images are ranges.\n"
                        "- OpenStreetMap roads and shelters are incomplete; the shelter list was hand-checked for the demo area.\n"
                        "- Research prototype, not an official warning system. Follow official alerts (BMD, FFWC, DDM)."),
        "people": "people", "isolated_count": "{n} villages ({p} people) isolated on {d}",
    },
    "bn": {
        "title": "সেফউইন্ডো", "tagline": "কোন গ্রাম কবে আশ্রয়কেন্দ্রের শেষ রাস্তা হারায়?",
        "language": "ভাষা", "supply": "পরিবারের মজুদ দিন (অনুমান)",
        "supply_help": "বিচ্ছিন্ন হওয়ার পর একটি পরিবারের কাছে কত দিনের খাবার ও পানি থাকে। এটি অনুমান, পরিমাপ নয়।",
        "date": "তারিখ", "showing": "মানচিত্রে {d} তারিখের বন্যা দেখানো হচ্ছে ({src})।",
        "no_obs": "এই তারিখের আগে কোনো পর্যবেক্ষণ নেই - প্রথমটি দেখানো হচ্ছে ({d})।",
        "unknown_note": "এলাকার {p}% অংশে ব্যবহারযোগ্য ছবি নেই (মেঘ) - ধূসর রঙে দেখানো।",
        "connected": "আশ্রয়কেন্দ্রের সাথে যুক্ত", "isolated": "বিচ্ছিন্ন (কোনো আশ্রয়কেন্দ্রে সড়ক নেই)",
        "uncertain": "অনিশ্চিত (রাস্তা মেঘে ঢাকা)", "boat_dependent": "নৌকা-নির্ভর (রাস্তা থেকে ৫০০ মি.-এর বেশি)",
        "urgent": "উদ্ধারকর্মীর দৃষ্টি - সবচেয়ে জরুরি গ্রাম", "rank": "#", "village": "গ্রাম",
        "pop": "জনসংখ্যা", "isolated_when": "বিচ্ছিন্ন", "deadline": "সাহায্যের শেষ সময়",
        "pick": "একটি গ্রাম বেছে নিন (বা মানচিত্রে ক্লিক করুন)", "none": "-",
        "panel": "গ্রামের বিবরণ", "isolation": "বিচ্ছিন্ন হওয়ার তারিখ",
        "never": "কোনো পর্যবেক্ষিত তারিখে বিচ্ছিন্ন নয়", "safe_exit": "শেষ নিরাপদ বের হওয়ার দিন",
        "route": "{s} পর্যন্ত সড়কপথে {km} কিমি", "no_exit": "নিরাপদ পথ পাওয়া যায়নি (প্রথম ছবিতেই বিচ্ছিন্ন)",
        "deadline_label": "সাহায্যের শেষ সময় (সারভাইভাল ঘড়ি)", "days_left": "{d} তারিখে আর {n} দিনের মজুদ বাকি",
        "deadline_passed": "{d} তারিখের {n} দিন আগে মজুদ শেষ", "not_yet": "{d} তারিখে এখনো বিচ্ছিন্ন নয়",
        "sms": "এসএমএস নমুনা", "rain": "দৈনিক বৃষ্টিপাত - নাসা জিপিএম আইএমইআরজি",
        "modis": "প্লাবিত এলাকা - নাসা মোডিস দৈনিক বন্যা তথ্য", "upstream": "মেঘালয় পাহাড় (উজান)",
        "local": "সুনামগঞ্জ", "sens": "সংবেদনশীলতা পরীক্ষা", "valid": "সংবাদ প্রতিবেদনের সাথে যাচাই",
        "limits": "এই প্রোটোটাইপের সীমাবদ্ধতা",
        "limits_text": ("- মজুদ দিন একটি অনুমান, পরিমাপ নয়।\n"
                        "- মেঘ ও রাডারের ত্রুটির কারণে বন্যা মানচিত্রে ফাঁক আছে; ছবির মাঝের দিনগুলো একটি সময়সীমা।\n"
                        "- ওপেনস্ট্রিটম্যাপের রাস্তা ও আশ্রয়কেন্দ্রের তথ্য অসম্পূর্ণ; ডেমো এলাকার তালিকা হাতে যাচাই করা।\n"
                        "- এটি গবেষণা প্রোটোটাইপ, সরকারি সতর্কবার্তা নয়। সরকারি সতর্কবার্তা মেনে চলুন।"),
        "people": "জন", "isolated_count": "{d} তারিখে {n}টি গ্রাম ({p} জন) বিচ্ছিন্ন",
    },
}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
BN_MONTHS = {5: "মে", 6: "জুন", 7: "জুলাই"}


def fmt_date(d, lang: str) -> str:
    if d is None or pd.isna(d):
        return "-"
    d = pd.Timestamp(d)
    if lang == "bn":
        return f"{str(d.day).translate(BN_DIGITS)} {BN_MONTHS.get(d.month, d.strftime('%b'))}"
    return d.strftime("%d %b")


def bn_num(x, lang: str) -> str:
    return str(x).translate(BN_DIGITS) if lang == "bn" else str(x)


# --- data ------------------------------------------------------------------------

@st.cache_data
def load(app_dir: str):
    d = Path(app_dir)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    villages = gpd.read_file(d / "villages.geojson")
    for c in ("last_connected", "first_isolated", "isolated_from_earliest", "reconnected", "safe_exit_date"):
        villages[c] = pd.to_datetime(villages[c])
    status = pd.read_csv(d / "village_status.csv", dtype={"village_id": str})
    shelters = gpd.read_file(d / "shelters.geojson")
    routes = gpd.read_file(d / "exit_routes.geojson")
    cut = gpd.read_file(d / "cut_roads.geojson")
    opt = {n: pd.read_csv(d / f) for n, f in [("rain", "rainfall_daily.csv"), ("modis", "modis_flood_area.csv"),
                                               ("sens", "sensitivity_summary.csv"), ("valid", "validation.csv")]
           if (d / f).exists()}
    return meta, villages, status, shelters, routes, cut, opt


def sms_text(v, route_km, shelter) -> str:
    name = v["name_bn"] if isinstance(v.get("name_bn"), str) and v["name_bn"] else v["name"]
    lo, hi = v["isolated_from_earliest"], v["first_isolated"]
    when = (f"{fmt_date(lo, 'bn')} - {fmt_date(hi, 'bn')}" if pd.notna(v["last_connected"])
            else f"{fmt_date(hi, 'bn')} বা তার আগে")
    route = f"সড়কপথে {bn_num(f'{route_km:.1f}', 'bn')} কিমি" if route_km is not None else "জানা নেই"
    return (f"সতর্কতা (পরীক্ষামূলক): {name} এর সড়ক যোগাযোগ {when} এর মধ্যে বিচ্ছিন্ন হতে পারে। "
            f"নিরাপদ পথ: {route}। নিকটতম আশ্রয়কেন্দ্র: {shelter or 'জানা নেই'}। সরকারি সতর্কবার্তা মেনে চলুন।")


def nearest_village(villages: gpd.GeoDataFrame, lat: float, lng: float, max_m: float = 400):
    dx = (villages.geometry.x - lng) * 111_320 * math.cos(math.radians(lat))
    dy = (villages.geometry.y - lat) * 110_540
    d = (dx ** 2 + dy ** 2) ** 0.5
    i = d.idxmin()
    return villages.loc[i, "village_id"] if d[i] <= max_m else None


# --- page --------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="SafeWindow", page_icon="🛶", layout="wide")
    paths = config.get_paths()
    if not (paths.app / "meta.json").exists():
        st.error(f"No app data in {paths.app}. Run `python scripts/run_engine.py` "
                 "(or make the demo with `python scripts/make_demo_data.py`).")
        st.stop()
    meta, villages, status, shelters, routes, cut, opt = load(str(paths.app))

    with st.sidebar:
        lang = "bn" if st.radio("Language / ভাষা", ["English", "বাংলা"], horizontal=True) == "বাংলা" else "en"
        t = T[lang]
        lo, hi = meta["supply_days_range"]
        supply = st.slider(t["supply"], lo, hi, meta["default_supply_days"], help=t["supply_help"])
        st.markdown("---")
        for k, c in STATUS_COLOR.items():
            st.markdown(f"<span style='color:{c};font-size:1.2em'>●</span> {t[k]}", unsafe_allow_html=True)
        st.markdown("<span style='color:#1e6ee6'>■</span> flood &nbsp; "
                    "<span style='color:#8c8c8c'>■</span> no data", unsafe_allow_html=True)
        with st.expander(t["limits"]):
            st.markdown(t["limits_text"])

    st.title(f"🛶 {t['title']}")
    st.caption(t["tagline"])
    if meta.get("data_label"):
        st.warning(f"⚠️ {meta['data_label']}")

    # Survival Clock depends on the slider, so deadlines are recomputed here
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(supply, unit="D")

    # --- date slider ---
    obs = pd.to_datetime(meta["dates"])
    days = pd.date_range(meta["app_start"], meta["app_end"]).date
    iso_counts = status[status["status"] == "isolated"].groupby("date").size()
    peak = pd.Timestamp(iso_counts.idxmax()).date() if len(iso_counts) else days[0]
    day = st.select_slider(t["date"], options=list(days), value=min(max(peak, days[0]), days[-1]),
                           format_func=lambda d: fmt_date(d, lang))
    past = obs[obs <= pd.Timestamp(day)]
    obs_day = (past.max() if len(past) else obs.min()).strftime("%Y-%m-%d")
    st.caption((t["showing"] if len(past) else t["no_obs"]).format(
        d=fmt_date(obs_day, lang), src=meta["sources"].get(obs_day, "")))
    if meta["unknown_pct"].get(obs_day, 0) >= 5:
        st.caption(t["unknown_note"].format(p=bn_num(round(meta["unknown_pct"][obs_day]), lang)))

    st_day = status[status["date"] == obs_day].set_index("village_id")["status"]
    villages["status_now"] = villages["village_id"].map(st_day).fillna("uncertain")
    iso_now = villages[villages["status_now"] == "isolated"]
    st.markdown("**" + t["isolated_count"].format(n=bn_num(len(iso_now), lang), d=fmt_date(obs_day, lang),
                p=bn_num(f"{int(iso_now['population'].sum()):,}", lang)) + "**")

    # --- selected village (from selectbox or map click) ---
    ranked = villages.sort_values(["urgency_rank", "name"], na_position="last")
    ids = [None] + ranked["village_id"].tolist()
    label = dict(zip(villages["village_id"], villages["name"]))
    if "village" not in st.session_state:
        st.session_state.village = None

    col_map, col_side = st.columns([2.2, 1])
    with col_map:
        b = meta["flood_bounds"][obs_day]
        centre = [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2]
        m = folium.Map(location=centre, zoom_start=12, tiles="CartoDB positron", control_scale=True)
        folium.raster_layers.ImageOverlay(
            str(paths.app / "flood" / f"{obs_day.replace('-', '')}.png"), bounds=b, opacity=0.75,
            name="Flood", interactive=False).add_to(m)
        cut_now = cut[cut["date"] == obs_day]
        if len(cut_now):
            folium.GeoJson(cut_now[["geometry"]], name="Cut roads",
                           style_function=lambda _: {"color": "#7a1020", "weight": 2, "opacity": 0.7}).add_to(m)
        sel = st.session_state.village
        if sel is not None:
            r = routes[routes["village_id"] == sel]
            if len(r):
                folium.GeoJson(r[["geometry"]], name="Exit route", style_function=lambda _: {
                    "color": "#0b8a3e", "weight": 6, "opacity": 0.9, "dashArray": "8 6"}).add_to(m)
        for s in shelters.itertuples():
            folium.Marker([s.geometry.y, s.geometry.x], tooltip=f"🏫 {s.name}",
                          icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(m)
        for v in villages.itertuples():
            pop = 0 if pd.isna(v.population) else v.population
            folium.CircleMarker(
                [v.geometry.y, v.geometry.x], radius=5 + min(pop, 8000) / 1200,
                color="#222" if v.village_id == sel else "white", weight=3 if v.village_id == sel else 1,
                fill=True, fill_color=STATUS_COLOR[v.status_now], fill_opacity=0.95,
                tooltip=f"{v.name} · {t[v.status_now]}").add_to(m)
        folium.LayerControl(collapsed=True).add_to(m)
        out = st_folium(m, height=560, use_container_width=True, returned_objects=["last_object_clicked"],
                        key="map")
        click = (out or {}).get("last_object_clicked")
        if click and click != st.session_state.get("last_click"):
            st.session_state.last_click = click
            hit = nearest_village(villages, click["lat"], click["lng"])
            if hit and hit != st.session_state.village:
                st.session_state.village = hit
                st.rerun()

    with col_side:
        st.subheader(t["urgent"])
        top = ranked[ranked["outcome"] == "isolated"].head(15)
        st.dataframe(pd.DataFrame({
            t["rank"]: top["urgency_rank"].astype(int),
            t["village"]: top["name"],
            t["pop"]: top["population"],
            t["isolated_when"]: [f"{fmt_date(a, lang)}–{fmt_date(b_, lang)}" if pd.notna(c) else f"≤ {fmt_date(b_, lang)}"
                                 for a, b_, c in zip(top["isolated_from_earliest"], top["first_isolated"],
                                                     top["last_connected"])],
            t["deadline"]: [fmt_date(d, lang) for d in top["aid_deadline"]],
        }), hide_index=True, height=420)
        choice = st.selectbox(t["pick"], ids, index=ids.index(st.session_state.village),
                              format_func=lambda i: t["none"] if i is None else label[i])
        if choice != st.session_state.village:
            st.session_state.village = choice
            st.rerun()

    if st.session_state.village is not None:
        village_panel(villages, routes, st.session_state.village, pd.Timestamp(day), lang, t)

    charts(opt, meta, pd.Timestamp(day), lang, t)

    c1, c2 = st.columns(2)
    if "sens" in opt:
        with c1.expander(t["sens"]):
            st.dataframe(opt["sens"], hide_index=True)
    if "valid" in opt:
        with c2.expander(t["valid"]):
            st.dataframe(opt["valid"], hide_index=True)


def village_panel(villages, routes, vid, day: pd.Timestamp, lang, t):
    v = villages[villages["village_id"] == vid].iloc[0]
    r = routes[routes["village_id"] == vid]
    route_km = r["length_m"].iloc[0] / 1000 if len(r) else None
    shelter = r["shelter_name"].iloc[0] if len(r) else None

    st.markdown("---")
    name = v["name_bn"] if lang == "bn" and isinstance(v.get("name_bn"), str) else v["name"]
    st.subheader(f"{t['panel']}: {name}")
    a, b, c, d = st.columns(4)
    a.metric(t["pop"], "-" if pd.isna(v["population"]) else bn_num(f"{int(v['population']):,}", lang))
    if v["outcome"] == "isolated":
        rng = (f"{fmt_date(v['isolated_from_earliest'], lang)} – {fmt_date(v['first_isolated'], lang)}"
               if pd.notna(v["last_connected"]) else f"≤ {fmt_date(v['first_isolated'], lang)}")
        b.metric(t["isolation"], rng)
        c.metric(t["safe_exit"], fmt_date(v["safe_exit_date"], lang))
        d.metric(t["deadline_label"], fmt_date(v["aid_deadline"], lang))
        if route_km is not None:
            st.success("🛣️ " + t["route"].format(km=bn_num(f"{route_km:.1f}", lang) if lang == "bn" else route_km,
                                                  s=shelter))
        else:
            st.info(t["no_exit"])
        if day >= v["isolated_from_earliest"]:
            left = (v["aid_deadline"] - day).days
            msg = (t["days_left"].format(n=bn_num(left, lang), d=fmt_date(day, lang)) if left >= 0 else
                   t["deadline_passed"].format(n=bn_num(-left, lang), d=fmt_date(day, lang)))
            (st.error if left <= 2 else st.warning)("⏳ " + msg)
        else:
            st.info(t["not_yet"].format(d=fmt_date(day, lang)))
        st.markdown(f"**{t['sms']}**")
        st.code(sms_text(v, route_km, shelter), language=None, wrap_lines=True)
    else:
        b.metric(t["isolation"], t[v["outcome"]] if v["outcome"] in t else t["never"])


def charts(opt, meta, day: pd.Timestamp, lang, t):
    c1, c2 = st.columns(2)
    rule = alt.Chart(pd.DataFrame({"date": [day]})).mark_rule(color="#d7263d", strokeWidth=2).encode(x="date:T")
    obs = alt.Chart(pd.DataFrame({"date": pd.to_datetime(meta["dates"])})).mark_tick(
        color="#555", thickness=2, size=10).encode(x="date:T")
    if "rain" in opt:
        r = opt["rain"].copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r[(r["date"] >= meta["app_start"]) & (r["date"] <= meta["app_end"])]
        long = r.melt("date", var_name="box", value_name="mm")
        long["box"] = long["box"].map({"meghalaya_upstream_mm": t["upstream"], "sunamganj_mm": t["local"]})
        bars = alt.Chart(long).mark_bar(opacity=0.85).encode(
            x=alt.X("date:T", title=None), xOffset="box:N",
            y=alt.Y("mm:Q", title="mm/day"),
            color=alt.Color("box:N", title=None, scale=alt.Scale(range=["#1f4e9c", "#7fb3e6"]),
                            legend=alt.Legend(orient="top")),
            tooltip=["date:T", "box:N", "mm:Q"])
        c1.markdown(f"**{t['rain']}**")
        c1.altair_chart((bars + rule).properties(height=220), use_container_width=True)
    if "modis" in opt:
        md = opt["modis"].copy()
        md["date"] = pd.to_datetime(md["date"])
        md = md[(md["date"] >= meta["app_start"]) & (md["date"] <= meta["app_end"])]
        line = alt.Chart(md).mark_area(color="#1e6ee6", opacity=0.35, line=True).encode(
            x=alt.X("date:T", title=None), y=alt.Y("flooded_km2:Q", title="km²"),
            tooltip=["date:T", "flooded_km2:Q", "unknown_pct:Q"])
        c2.markdown(f"**{t['modis']}**")
        c2.altair_chart((line + rule + obs).properties(height=220), use_container_width=True)


main()
