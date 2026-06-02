"""Pagina Mappa — annunci di Milano plottati con pydeck.

Marker colorati per tipo (private=verde, agency=blu).
Tooltip con annuncio, prezzo, telefono.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402

from lib import get_contacts_df, get_listing_contacts_df, get_listings_df, setup_page  # noqa: E402

setup_page("Mappa", icon="🗺️")
st.title("🗺️ Mappa annunci")
st.caption("Privati (🟢) e agenzie (🔵) plottati sulla mappa di Milano")

listings = get_listings_df()
contacts = get_contacts_df()
lc = get_listing_contacts_df()

if listings.empty:
    st.warning("Nessun annuncio.")
    st.stop()

# Solo geocodificati e attivi
geo = listings[
    listings["latitude"].notna()
    & listings["longitude"].notna()
    & ((listings["status"] == "active") if "status" in listings.columns else True)
].copy()

n_total_active = len(listings[listings["status"] == "active"]) if "status" in listings.columns else len(listings)
geo_pct = len(geo) / max(1, n_total_active)
st.caption(f"📍 {len(geo)} / {n_total_active} annunci geocodificati ({geo_pct:.0%})")
if geo_pct < 0.5:
    st.info(
        "Per riempire le coordinate Idealista mancanti, lancia: "
        "`python scripts/geocode_listings.py`"
    )

# Sidebar filtri
st.sidebar.header("Filtri mappa")
sel_portals = st.sidebar.multiselect(
    "Portale",
    sorted(geo["portal"].dropna().unique().tolist()),
    default=sorted(geo["portal"].dropna().unique().tolist()),
)
sel_adv = st.sidebar.multiselect(
    "Inserzionista",
    sorted(geo["advertiser_type"].dropna().unique().tolist()),
    default=sorted(geo["advertiser_type"].dropna().unique().tolist()),
)
prices = geo["price_eur"].dropna()
if not prices.empty:
    pmin, pmax = int(prices.min()), int(prices.max())
    price_range = st.sidebar.slider("Prezzo €/mese", pmin, pmax, (pmin, pmax))
else:
    price_range = None

filt = geo.copy()
if sel_portals:
    filt = filt[filt["portal"].isin(sel_portals)]
if sel_adv:
    filt = filt[filt["advertiser_type"].isin(sel_adv)]
if price_range:
    pmin, pmax = price_range
    filt = filt[(filt["price_eur"].isna())
                | ((filt["price_eur"] >= pmin) & (filt["price_eur"] <= pmax))]

# Join contatti per tooltip (telefono dell'inserzionista)
if not lc.empty and not contacts.empty:
    contact_phone = (
        lc.merge(contacts[["id", "phone_e164", "display_name"]],
                 left_on="contact_id", right_on="id")
        .groupby("listing_id")
        .agg({"phone_e164": "first", "display_name": "first"})
        .reset_index()
    )
    filt = filt.merge(
        contact_phone, left_on="id", right_on="listing_id", how="left",
    )

# Color per tipo
def color_for(adv_type: str) -> list[int]:
    if adv_type == "private":
        return [46, 125, 50, 200]   # verde
    if adv_type == "agency":
        return [25, 118, 210, 180]  # blu
    return [158, 158, 158, 180]     # grigio

filt["color"] = filt["advertiser_type"].apply(color_for)

# Radius proporzionale al prezzo (visual hint), default 30
filt["radius"] = (filt["price_eur"].fillna(1000) / 30).clip(20, 150)

# ----------------------------------------------------------------------------
# Pydeck map
# ----------------------------------------------------------------------------

view = pdk.ViewState(
    latitude=45.4642,
    longitude=9.1900,
    zoom=11.5,
    pitch=0,
)

# Sostituzione manuale dei NaN per tooltip pulito
def safe(v, fallback="—"):
    return v if pd.notna(v) else fallback

filt_d = filt.copy()
filt_d["title_s"] = filt_d.get("title", "").fillna("").astype(str).str.slice(0, 80)
filt_d["zone_s"] = filt_d.get("microzone", "").fillna("—")
filt_d["price_s"] = filt_d.get("price_eur", "").apply(
    lambda v: f"{int(v)} €/mese" if pd.notna(v) else "n/d"
)
filt_d["surface_s"] = filt_d.get("surface_m2", "").apply(
    lambda v: f"{int(v)} m²" if pd.notna(v) else ""
)
filt_d["phone_s"] = filt_d.get("phone_e164", "").fillna("n/d")
filt_d["name_s"] = filt_d.get("display_name", "").fillna(
    filt_d.get("advertiser_name", "").fillna("—")
)
filt_d["url_s"] = filt_d.get("url", "")

layer = pdk.Layer(
    "ScatterplotLayer",
    data=filt_d[["latitude", "longitude", "color", "radius",
                 "title_s", "zone_s", "price_s", "surface_s",
                 "phone_s", "name_s", "url_s", "portal", "advertiser_type"]],
    get_position="[longitude, latitude]",
    get_fill_color="color",
    get_radius="radius",
    radius_min_pixels=3,
    radius_max_pixels=30,
    pickable=True,
    auto_highlight=True,
)

tooltip = {
    "html": (
        "<b>{title_s}</b><br/>"
        "📍 {zone_s}<br/>"
        "💰 {price_s} · {surface_s}<br/>"
        "👤 {name_s}<br/>"
        "📞 {phone_s}<br/>"
        "<i>{portal} · {advertiser_type}</i>"
    ),
    "style": {
        "backgroundColor": "white",
        "color": "#212121",
        "padding": "8px",
        "borderRadius": "6px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.2)",
        "fontSize": "12px",
    },
}

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9",
    ),
    height=620,
)

# ----------------------------------------------------------------------------
# Density (heatmap) opzionale
# ----------------------------------------------------------------------------

st.divider()
if st.checkbox("🔥 Mostra anche heatmap concentrazione"):
    heat = pdk.Layer(
        "HeatmapLayer",
        data=filt[["latitude", "longitude"]],
        get_position="[longitude, latitude]",
        radius_pixels=40,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[heat],
            initial_view_state=view,
            map_style="mapbox://styles/mapbox/light-v9",
        ),
        height=520,
    )

st.caption(
    f"Visualizzati {len(filt)} annunci · "
    "cerchio = posizione · raggio ~ prezzo · "
    "tooltip su hover"
)
