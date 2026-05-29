"""Dashboard BOT_IMMOBILIARE — pagina Home con KPI e grafici aggregati.

Lancio:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.lib import (
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

# ----------------------------------------------------------------------------
# Carica dati
# ----------------------------------------------------------------------------

listings = get_listings_df()
contacts = get_contacts_df()
outreach = get_outreach_df()

if listings.empty:
    st.warning("Nessun dato ancora — esegui `scripts/run_cycle.py` per popolare il DB.")
    st.stop()


# ----------------------------------------------------------------------------
# KPI ROW
# ----------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)

n_listings = len(listings)
n_listings_priv = len(listings[listings["advertiser_type"] == "private"])
n_contacts = len(contacts)
n_contacts_priv = len(contacts[contacts["kind"] == "private"]) if "kind" in contacts.columns else 0
n_contacts_with_phone = len(contacts[contacts["phone_e164"].notna()]) if not contacts.empty else 0

if not outreach.empty:
    n_queued = len(outreach[outreach["status"] == "queued"])
    n_sent = len(outreach[outreach["status"].isin(["sent", "delivered"])])
else:
    n_queued = 0
    n_sent = 0

kpi(c1, "Annunci totali", f"{n_listings:,}",
    help="Tutti i listings monitorati (Idealista + Immobiliare)")
kpi(c2, "Annunci privati", f"{n_listings_priv:,}",
    help="Solo advertiser_type=private")
kpi(c3, "Contatti unici", f"{n_contacts:,}",
    delta=f"{n_contacts_priv} privati" if n_contacts_priv else None,
    help="Dedup su phone_e164 / email")
kpi(c4, "Outreach in coda", f"{n_queued:,}",
    help="Messaggi accodati, non ancora inviati")
kpi(c5, "Outreach inviati", f"{n_sent:,}",
    help="Sent + delivered nel canale")

st.divider()

# ----------------------------------------------------------------------------
# GRAFICI
# ----------------------------------------------------------------------------

g1, g2 = st.columns(2)

with g1:
    st.subheader("Annunci per portale × inserzionista")
    df_pivot = (
        listings.groupby(["portal", "advertiser_type"])
        .size()
        .reset_index(name="count")
    )
    fig = px.bar(
        df_pivot, x="portal", y="count", color="advertiser_type",
        color_discrete_map={"private": "#2E7D32", "agency": "#90A4AE"},
        text="count",
    )
    fig.update_layout(height=350, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with g2:
    st.subheader("Distribuzione prezzi affitti (€/mese)")
    prices = listings["price_eur"].dropna()
    if not prices.empty:
        fig = px.histogram(
            prices, nbins=30,
            color_discrete_sequence=["#2E7D32"],
        )
        fig.update_layout(
            height=350, showlegend=False, margin=dict(t=10, l=0, r=0, b=0),
            xaxis_title="€/mese", yaxis_title="annunci",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nessun prezzo disponibile")

st.divider()

# Top zone Milano
g3, g4 = st.columns(2)

with g3:
    st.subheader("Top 15 microzone (Idealista)")
    zone_col = "microzone"
    zone_data = (
        listings[listings[zone_col].notna() & (listings[zone_col] != "")]
        .groupby(zone_col)
        .size()
        .reset_index(name="annunci")
        .sort_values("annunci", ascending=False)
        .head(15)
    )
    if not zone_data.empty:
        fig = px.bar(
            zone_data, x="annunci", y=zone_col, orientation="h",
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
    st.subheader("Outreach funnel")
    if outreach.empty:
        st.info("Nessun outreach ancora")
    else:
        status_counts = outreach["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        # Order
        order = ["queued", "sent", "delivered", "replied", "opted_out", "failed"]
        status_counts["order"] = status_counts["status"].map(
            {s: i for i, s in enumerate(order)}
        )
        status_counts = status_counts.sort_values("order").drop("order", axis=1)
        fig = px.funnel(
            status_counts, x="count", y="status",
            color_discrete_sequence=["#2E7D32"],
        )
        fig.update_layout(height=420, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Annunci nel tempo
st.subheader("Nuovi annunci nel tempo (per first_seen)")
if "first_seen_at" in listings.columns:
    timeline = (
        listings.assign(day=listings["first_seen_at"].dt.floor("h"))
        .groupby(["day", "portal"])
        .size()
        .reset_index(name="annunci")
    )
    fig = px.line(
        timeline, x="day", y="annunci", color="portal",
        markers=True,
        color_discrete_map={"idealista": "#2E7D32", "immobiliare": "#1976D2"},
    )
    fig.update_layout(height=300, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)
