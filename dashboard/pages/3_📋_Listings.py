"""Pagina Listings: tabella filtrabile + dettaglio annuncio."""

from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import get_listings_df, setup_page  # noqa: E402

setup_page("Listings", icon="📋")
st.title("📋 Annunci")

df = get_listings_df()
if df.empty:
    st.warning("Nessun annuncio ancora. Esegui `scripts/run_cycle.py`.")
    st.stop()

# ----------------------------------------------------------------------------
# Sidebar — filtri
# ----------------------------------------------------------------------------

st.sidebar.header("Filtri")

portals = sorted(df["portal"].dropna().unique().tolist())
sel_portals = st.sidebar.multiselect("Portale", portals, default=portals)

adv_types = sorted(df["advertiser_type"].dropna().unique().tolist())
sel_adv = st.sidebar.multiselect(
    "Inserzionista", adv_types, default=adv_types,
    help="private = obiettivo principale del bot"
)

# Status
statuses = sorted(df["status"].dropna().unique().tolist()) if "status" in df.columns else ["active"]
sel_status = st.sidebar.multiselect("Status", statuses, default=["active"] if "active" in statuses else statuses)

prices = df["price_eur"].dropna()
if not prices.empty:
    pmin, pmax = int(prices.min()), int(prices.max())
    price_range = st.sidebar.slider(
        "Prezzo €/mese", pmin, pmax, (pmin, min(pmax, 5000))
    )
else:
    price_range = None

zones = sorted(df["microzone"].dropna().unique().tolist())
sel_zones = st.sidebar.multiselect("Zona (microzone)", zones)

text_search = st.sidebar.text_input("Cerca nel titolo / descrizione")

# ----------------------------------------------------------------------------
# Apply
# ----------------------------------------------------------------------------

filt = df.copy()
if sel_portals:
    filt = filt[filt["portal"].isin(sel_portals)]
if sel_adv:
    filt = filt[filt["advertiser_type"].isin(sel_adv)]
if sel_status and "status" in filt.columns:
    filt = filt[filt["status"].isin(sel_status)]
if price_range:
    pmin, pmax = price_range
    filt = filt[(filt["price_eur"].isna()) |
                ((filt["price_eur"] >= pmin) & (filt["price_eur"] <= pmax))]
if sel_zones:
    filt = filt[filt["microzone"].isin(sel_zones)]
if text_search:
    mask = (
        filt["title"].str.contains(text_search, case=False, na=False)
        | filt["description"].str.contains(text_search, case=False, na=False)
    )
    filt = filt[mask]

st.caption(f"**{len(filt):,}** annunci visibili (di {len(df):,} totali)")

# ----------------------------------------------------------------------------
# Tabella
# ----------------------------------------------------------------------------

display_cols = [
    "portal", "advertiser_type", "advertiser_name",
    "title", "price_eur", "surface_m2", "rooms",
    "microzone", "macrozone",
    "url", "first_seen_at", "last_seen_at", "scraped_count",
]
display_cols = [c for c in display_cols if c in filt.columns]

st.dataframe(
    filt[display_cols],
    use_container_width=True,
    height=520,
    column_config={
        "url": st.column_config.LinkColumn("Annuncio", display_text="🔗 apri"),
        "price_eur": st.column_config.NumberColumn("€/mese", format="€ %d"),
        "surface_m2": st.column_config.NumberColumn("m²"),
        "advertiser_type": st.column_config.TextColumn("Tipo"),
        "first_seen_at": st.column_config.DatetimeColumn("Primo visto", format="DD/MM/YY HH:mm"),
        "last_seen_at": st.column_config.DatetimeColumn("Ultimo visto", format="DD/MM/YY HH:mm"),
    },
    hide_index=True,
)

# Export CSV
csv = filt[display_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Esporta CSV", csv,
    file_name="listings_export.csv", mime="text/csv",
)
