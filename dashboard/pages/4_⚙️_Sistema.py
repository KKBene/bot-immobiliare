"""Pagina Sistema: salute del bot, errori, attività recente."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from lib import (  # noqa: E402
    get_contacts_df,
    get_listings_df,
    get_outreach_df,
    setup_page,
)

setup_page("Sistema", icon="⚙️")
st.title("⚙️ Sistema")
st.caption("Salute del bot, attività recente, configurazione")

listings = get_listings_df()
contacts = get_contacts_df()
outreach = get_outreach_df()

# ----------------------------------------------------------------------------
# Ultimo scrape (per portale)
# ----------------------------------------------------------------------------

st.subheader("📡 Ultimo scrape per portale")
if not listings.empty and "last_seen_at" in listings.columns:
    last_by_portal = (
        listings.groupby("portal")["last_seen_at"]
        .max()
        .reset_index()
        .rename(columns={"last_seen_at": "ultimo_scrape"})
    )
    last_by_portal["minuti_fa"] = (
        (pd.Timestamp.now(tz="UTC") - last_by_portal["ultimo_scrape"])
        .dt.total_seconds() / 60
    ).round(1)
    st.dataframe(
        last_by_portal,
        hide_index=True,
        use_container_width=True,
        column_config={
            "ultimo_scrape": st.column_config.DatetimeColumn(
                "Ultimo scrape", format="DD/MM HH:mm"
            ),
            "minuti_fa": st.column_config.NumberColumn(
                "Minuti fa", format="%.1f min"
            ),
        },
    )
    max_age = last_by_portal["minuti_fa"].max()
    if max_age > 240:
        st.error(f"⚠️ Ultimo scrape > 4h fa — verifica GitHub Actions workflow")
    elif max_age > 180:
        st.warning(f"Ultimo scrape > 3h fa — il cron dovrebbe scattare a breve")
    else:
        st.success("Tutto in orario")

st.divider()

# ----------------------------------------------------------------------------
# Activity nel tempo
# ----------------------------------------------------------------------------

st.subheader("📈 Annunci scoperti per giorno (ultimi 14 giorni)")
if not listings.empty:
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=14)
    recent = listings[listings["first_seen_at"] >= cutoff].copy()
    if not recent.empty:
        recent["day"] = recent["first_seen_at"].dt.date
        by_day = (
            recent.groupby(["day", "portal", "advertiser_type"])
            .size()
            .reset_index(name="annunci")
        )
        fig = px.bar(
            by_day, x="day", y="annunci",
            color="portal", facet_row="advertiser_type",
            color_discrete_map={"idealista": "#2E7D32", "immobiliare": "#1976D2"},
            text="annunci",
        )
        fig.update_layout(height=460, margin=dict(t=20, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Distribuzione scrape_count (re-scrape efficacy)
# ----------------------------------------------------------------------------

g1, g2 = st.columns(2)

with g1:
    st.subheader("🔄 Re-scrape efficacy")
    if "scraped_count" in listings.columns:
        sc = listings["scraped_count"].value_counts().reset_index()
        sc.columns = ["scraped_count", "n_listings"]
        sc = sc.sort_values("scraped_count")
        fig = px.bar(
            sc, x="scraped_count", y="n_listings",
            color_discrete_sequence=["#2E7D32"],
        )
        fig.update_layout(
            height=300, margin=dict(t=10, l=0, r=0, b=0),
            xaxis_title="Quante volte visto", yaxis_title="annunci",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "1 = visto una sola volta · valori alti = annuncio attivo da tempo"
        )

with g2:
    st.subheader("📊 Status listings")
    if "status" in listings.columns:
        sc = listings.groupby(["portal", "status"]).size().reset_index(name="n")
        fig = px.bar(
            sc, x="portal", y="n", color="status", text="n",
            color_discrete_map={"active": "#2E7D32", "removed": "#9E9E9E"},
        )
        fig.update_layout(height=300, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Outreach summary
# ----------------------------------------------------------------------------

st.subheader("📨 Outreach (riepilogo veloce)")
if outreach.empty:
    st.info("Nessun outreach ancora.")
else:
    cc = outreach["status"].value_counts().reset_index()
    cc.columns = ["status", "n"]
    st.dataframe(cc, hide_index=True, use_container_width=False)

st.divider()

# ----------------------------------------------------------------------------
# Config & ambiente
# ----------------------------------------------------------------------------

st.subheader("🔧 Configurazione")
import os
config_rows = [
    ("Supabase URL", os.environ.get("SUPABASE_URL", "")[:50] + "…"),
    ("Telegram", "✅ attivo" if os.environ.get("TELEGRAM_BOT_TOKEN") else "❌ non configurato"),
    ("Twilio", "✅ attivo" if os.environ.get("TWILIO_ACCOUNT_SID") else "❌ non configurato"),
]
st.table(pd.DataFrame(config_rows, columns=["Servizio", "Stato"]))

st.caption(
    "👉 Per cambiare config: modifica il `.env` (locale) oppure i Secrets "
    "(Streamlit Cloud Settings → Secrets / GitHub Settings → Actions Secrets)."
)
