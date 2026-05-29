"""Dashboard BOT_IMMOBILIARE — Home con KPI, freshness, e grafici aggregati."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from lib import (  # noqa: E402
    get_contacts_df,
    get_listings_df,
    get_outreach_df,
    kpi,
    setup_page,
)

setup_page("Home", icon="🏠")

st.title("🏠 BOT_IMMOBILIARE")
st.caption(
    "Monitor affitti Milano · Idealista + Immobiliare · "
    "lead pipeline per affitti medio termine"
)

# Refresh button
ctop = st.columns([6, 1])
with ctop[1]:
    if st.button("🔄 Refresh", use_container_width=True):
        from lib import clear_caches
        clear_caches()
        st.rerun()

# ----------------------------------------------------------------------------
# Carica dati
# ----------------------------------------------------------------------------

listings = get_listings_df()
contacts = get_contacts_df()
outreach = get_outreach_df()

if listings.empty:
    st.warning("Nessun dato ancora — esegui `scripts/run_cycle.py` per popolare il DB.")
    st.stop()

now = pd.Timestamp.now(tz="UTC")
last_24h = now - pd.Timedelta(hours=24)
last_7d = now - pd.Timedelta(days=7)

# ----------------------------------------------------------------------------
# KPI ROW 1 — Totali
# ----------------------------------------------------------------------------

active = listings[listings["status"] == "active"] if "status" in listings.columns else listings
listings_24h = active[active["first_seen_at"] >= last_24h]
priv_listings = active[active["advertiser_type"] == "private"]
priv_listings_24h = listings_24h[listings_24h["advertiser_type"] == "private"]

c1, c2, c3, c4, c5 = st.columns(5)
kpi(c1, "Annunci attivi", f"{len(active):,}",
    delta=f"+{len(listings_24h)} ultime 24h" if len(listings_24h) else None)
kpi(c2, "Privati attivi", f"{len(priv_listings):,}",
    delta=f"+{len(priv_listings_24h)} ultime 24h" if len(priv_listings_24h) else None,
    help="L'obiettivo primario del bot")
contacts_priv_with_phone = contacts[
    (contacts.get("kind") == "private") & contacts["phone_e164"].notna()
] if not contacts.empty else pd.DataFrame()
kpi(c3, "Lead pronti", f"{len(contacts_priv_with_phone):,}",
    help="Contatti privati con telefono, non opt-out")

if not outreach.empty:
    n_queued = len(outreach[outreach["status"] == "queued"])
    n_sent = len(outreach[outreach["status"].isin(["sent", "delivered"])])
else:
    n_queued = n_sent = 0
kpi(c4, "SMS in coda", f"{n_queued:,}")
kpi(c5, "SMS inviati", f"{n_sent:,}")

st.divider()

# ----------------------------------------------------------------------------
# Nuovi privati ultimi 7 giorni (lista veloce)
# ----------------------------------------------------------------------------

st.subheader("⚡ Privati nuovi negli ultimi 7 giorni")

priv_7d = active[
    (active["advertiser_type"] == "private")
    & (active["first_seen_at"] >= last_7d)
].sort_values("first_seen_at", ascending=False)

if priv_7d.empty:
    st.info("Nessun nuovo privato negli ultimi 7 giorni. Il bot continuerà a monitorare.")
else:
    show_cols = [
        "first_seen_at", "advertiser_name", "microzone",
        "price_eur", "surface_m2", "rooms", "url",
    ]
    show_cols = [c for c in show_cols if c in priv_7d.columns]
    st.dataframe(
        priv_7d[show_cols].head(20),
        hide_index=True,
        use_container_width=True,
        column_config={
            "first_seen_at": st.column_config.DatetimeColumn(
                "Quando", format="DD/MM HH:mm"
            ),
            "advertiser_name": st.column_config.TextColumn("Inserzionista"),
            "microzone": st.column_config.TextColumn("Zona"),
            "price_eur": st.column_config.NumberColumn("€/mese", format="€ %d"),
            "surface_m2": st.column_config.NumberColumn("m²"),
            "rooms": st.column_config.TextColumn("Locali"),
            "url": st.column_config.LinkColumn("Annuncio", display_text="🔗 apri"),
        },
    )
    st.caption(
        f"👉 Vai alla pagina **🎯 Lead** per vederli con telefono e bottoni "
        f"Chiama / WhatsApp."
    )

st.divider()

# ----------------------------------------------------------------------------
# GRAFICI
# ----------------------------------------------------------------------------

g1, g2 = st.columns(2)

with g1:
    st.subheader("Annunci per portale × inserzionista")
    df_pivot = (
        active.groupby(["portal", "advertiser_type"])
        .size()
        .reset_index(name="count")
    )
    fig = px.bar(
        df_pivot, x="portal", y="count", color="advertiser_type",
        color_discrete_map={"private": "#2E7D32", "agency": "#90A4AE"},
        text="count",
    )
    fig.update_layout(height=330, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with g2:
    st.subheader("Distribuzione prezzi (€/mese)")
    prices = active["price_eur"].dropna()
    if not prices.empty:
        fig = px.histogram(
            prices, nbins=30, color_discrete_sequence=["#2E7D32"],
        )
        fig.update_layout(
            height=330, showlegend=False, margin=dict(t=10, l=0, r=0, b=0),
            xaxis_title="€/mese", yaxis_title="annunci",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nessun prezzo disponibile")

# Top zone Milano
g3, g4 = st.columns(2)

with g3:
    st.subheader("Top 15 microzone (annunci totali)")
    zone_data = (
        active[active["microzone"].notna() & (active["microzone"] != "")]
        .groupby("microzone")
        .size()
        .reset_index(name="annunci")
        .sort_values("annunci", ascending=False)
        .head(15)
    )
    if not zone_data.empty:
        fig = px.bar(
            zone_data, x="annunci", y="microzone", orientation="h",
            color_discrete_sequence=["#2E7D32"],
        )
        fig.update_layout(
            height=420, margin=dict(t=10, l=0, r=0, b=0),
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nessuna zona disponibile")

with g4:
    st.subheader("Top zone PRIVATI")
    pz = (
        active[
            (active["advertiser_type"] == "private")
            & active["microzone"].notna() & (active["microzone"] != "")
        ]
        .groupby("microzone")
        .size()
        .reset_index(name="annunci")
        .sort_values("annunci", ascending=False)
        .head(15)
    )
    if pz.empty:
        st.info("Nessun privato con zona ancora")
    else:
        fig = px.bar(
            pz, x="annunci", y="microzone", orientation="h",
            color_discrete_sequence=["#FF6F00"],
        )
        fig.update_layout(
            height=420, margin=dict(t=10, l=0, r=0, b=0),
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Annunci nel tempo
st.subheader("Nuovi annunci nel tempo (per ora)")
if "first_seen_at" in active.columns and not active.empty:
    timeline = (
        active.assign(slot=active["first_seen_at"].dt.floor("h"))
        .groupby(["slot", "portal"])
        .size()
        .reset_index(name="annunci")
    )
    fig = px.line(
        timeline, x="slot", y="annunci", color="portal", markers=True,
        color_discrete_map={"idealista": "#2E7D32", "immobiliare": "#1976D2"},
    )
    fig.update_layout(height=300, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

# Footer info
st.caption(
    f"📊 Aggiornato: cache {pd.Timestamp.now(tz='UTC').strftime('%H:%M:%S UTC')} · "
    f"TTL 60s · Forza refresh col bottone in alto"
)
