"""Pagina Outreach: log messaggi + funnel + dettaglio singolo messaggio."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard.lib import (
    get_contacts_df,
    get_listings_df,
    get_outreach_df,
    setup_page,
)

setup_page("Outreach", icon="📨")
st.title("📨 Outreach")

outreach = get_outreach_df()
contacts = get_contacts_df()
listings = get_listings_df()

if outreach.empty:
    st.warning(
        "Nessun outreach ancora. Esegui `scripts/run_step6.py --queue` per "
        "accodare i primi messaggi."
    )
    st.stop()

# Join con contacts e listings per leggibilità
if not contacts.empty:
    outreach = outreach.merge(
        contacts[["id", "phone_e164", "display_name", "kind"]],
        left_on="contact_id", right_on="id", how="left",
        suffixes=("", "_contact"),
    )
if not listings.empty:
    outreach = outreach.merge(
        listings[["id", "url", "title", "microzone", "portal"]],
        left_on="listing_id", right_on="id", how="left",
        suffixes=("", "_listing"),
    )

# ----------------------------------------------------------------------------
# KPI riga
# ----------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Totale messaggi", len(outreach))
c2.metric("In coda", len(outreach[outreach["status"] == "queued"]))
c3.metric("Inviati", len(outreach[outreach["status"].isin(["sent", "delivered"])]))
c4.metric("Risposti", len(outreach[outreach["status"] == "replied"]))

# ----------------------------------------------------------------------------
# Funnel + Channel
# ----------------------------------------------------------------------------

g1, g2 = st.columns(2)

with g1:
    st.subheader("Funnel status")
    order = ["queued", "sent", "delivered", "replied", "opted_out", "failed"]
    sc = outreach["status"].value_counts().reset_index()
    sc.columns = ["status", "count"]
    sc["order"] = sc["status"].map({s: i for i, s in enumerate(order)})
    sc = sc.sort_values("order").drop("order", axis=1)
    fig = px.funnel(sc, x="count", y="status",
                    color_discrete_sequence=["#2E7D32"])
    fig.update_layout(height=320, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with g2:
    st.subheader("Per canale")
    cc = outreach.groupby(["channel", "status"]).size().reset_index(name="count")
    fig = px.bar(cc, x="channel", y="count", color="status", text="count")
    fig.update_layout(height=320, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Sidebar filtri
# ----------------------------------------------------------------------------

st.sidebar.header("Filtri log")
channels = sorted(outreach["channel"].dropna().unique().tolist())
sel_ch = st.sidebar.multiselect("Canale", channels, default=channels)
statuses = sorted(outreach["status"].dropna().unique().tolist())
sel_st = st.sidebar.multiselect("Status", statuses, default=statuses)

filt = outreach.copy()
if sel_ch:
    filt = filt[filt["channel"].isin(sel_ch)]
if sel_st:
    filt = filt[filt["status"].isin(sel_st)]

# ----------------------------------------------------------------------------
# Log table
# ----------------------------------------------------------------------------

st.subheader(f"Log ({len(filt):,})")

display_cols = [
    "queued_at", "sent_at", "channel", "status",
    "display_name", "phone_e164", "kind",
    "microzone", "url",
    "message", "provider_id", "error",
]
display_cols = [c for c in display_cols if c in filt.columns]

st.dataframe(
    filt[display_cols].sort_values("queued_at", ascending=False),
    use_container_width=True,
    height=420,
    column_config={
        "url": st.column_config.LinkColumn("Annuncio", display_text="🔗"),
        "queued_at": st.column_config.DatetimeColumn("Accodato", format="DD/MM HH:mm"),
        "sent_at": st.column_config.DatetimeColumn("Inviato", format="DD/MM HH:mm"),
        "message": st.column_config.TextColumn("Messaggio", width="large"),
        "phone_e164": st.column_config.TextColumn("Telefono"),
    },
    hide_index=True,
)
