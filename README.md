# safewindow
Predicts when flood-hit villages in Bangladesh's haor region get cut off from shelters, and when aid must arrive. SAR flood maps + road network graph analysis. NASA Space Apps 2026.
SafeWindow 🌊

When will a flood-hit village be cut off, and when must aid arrive?

SafeWindow tells each flood-affected village in Bangladesh's haor region the date it loses its last road to safety, the last safe exit route, and a deadline for aid. It combines satellite radar flood maps with road-network analysis.

Built for the NASA Space Apps Challenge 2026. Status: concept and early prototype. This is a research project, not an official warning system. Always follow official alerts.

The Problem

In Sunamganj and other haor areas of Bangladesh, floods often hurt people by cutting villages off from shelters, hospitals, and aid. In 2022, floods in Sylhet and Sunamganj left millions of people stranded.

Most flood tools show where the water is. Very few say when a village loses access, or how long it can survive. Aid planners need that deadline.

Our Solution

For each village, SafeWindow calculates three things:

Output	Meaning
Isolation date	The first day no road path to a shelter remains
Safe exit window	The last day, and the route, a village can still use to reach a shelter
Aid deadline	Isolation date + days of food and water supply (adjustable)

Villages are then ranked by urgency, so responders know who needs help first.

How It Works
Satellite radar (SAR)  ──►  Flood map for each date
                                   │
OpenStreetMap roads    ──►  Road network graph
                                   │
                    Remove flooded roads for each date
                                   │
         Which villages can no longer reach any shelter?
                                   │
     Isolation date ─► Exit route ─► Aid deadline ─► Urgency ranking
Flood maps: Radar sees water through monsoon clouds. We map flood extent for several dates of a flood event.
Road graph: Roads, villages, and shelters come from OpenStreetMap, with a hand-checked shelter list for the demo area.
Cut flooded roads: For each date, roads under water are removed from the graph.
Isolation check: A village is isolated when no connected path to any shelter remains.
Survival Clock: An adjustable supply assumption (days of food and water) gives the aid deadline.
What the User Sees
A map with a date slider that replays the flood, with villages turning red as they are cut off
A village panel with isolation date, exit route, and aid deadline
A responder view ranking villages by urgency
Bangla and English text, plus a short SMS-style alert
Data Sources

NASA

NASA-ISRO NISAR (synthetic aperture radar), subject to data availability
GPM IMERG (rainfall)
MODIS Global Flood Product (MCDWD)
NASA Worldview (visual context)

Partner and open data

ESA Sentinel-1 (radar)
UNOSAT flood extent maps
OpenStreetMap (roads, villages, shelters)
WorldPop (population)
Copernicus DEM (elevation)
Tech Stack

Python · Google Earth Engine · osmnx · networkx · geopandas · rasterio · Streamlit · folium · QGIS

Project Structure (planned)
safewindow/
├── data/          # raw inputs, flood maps, outputs
├── notebooks/     # data preparation and analysis
├── safewindow/    # core code: flood, graph, survival clock
├── app.py         # Streamlit web app
├── PLAN.md        # full build plan
└── README.md
Roadmap
 Project idea, method, and build plan
 Confirm flood maps for 4–5 dates and a usable road graph
 Compute isolation dates and sanity-check
 Survival Clock and interactive map app
 Validate against news and public reports of isolated areas
 Optional: test whether rainfall predicts flood extent a few days ahead
Validation Plan

We will compare predicted isolation dates with news and public reports of isolated areas, and report the error openly. There is no perfect ground truth, and we will say so.

Limitations
Supply duration is an assumption, not measured data.
Flood maps can have gaps from clouds and radar errors.
OpenStreetMap shelter data may be incomplete, so we use a hand-checked list for the demo area.
This is a research prototype, not an official warning system.
What Makes It Different

The output is a deadline, not a risk map. To our knowledge, SafeWindow is among the first tools to combine satellite flood data, road-network analysis, and supply timing in one tool for Bangladesh.

Team
Name	Role
Name	Data and GIS
Name	Algorithm and Backend
Name	Frontend and Visuals
Name	Story and Design
License

MIT License. See LICENSE.
