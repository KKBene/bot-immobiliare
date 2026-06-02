"""Analisi temporale — trend, confronti, top zone, conversione.

Risponde alle domande operative di Paolo:
  - Quanti nuovi annunci privati al giorno?
  - Quanti da Idealista vs Immobiliare?
  - In che giorni della settimana / ore si concentrano le pubblicazioni?
  - Confronto periodo selezionato vs periodo precedente identico
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from lib import (  # noqa: E402
    get_contacts_df,
    get_listings_df,
    get_outreach_df,
    setup_page,
)

setup_page("Analisi", icon="📈")
st.title("📈 Analisi temporale")
st.caption("Trend giornaliero, confronto periodi, conversione lead")

listings = get_listings_df()
contacts = get_contacts_df()
outreach = get_outreach_df()

if listings.empty:
    st.warning("Niente dati ancora. Lancia `scripts/run_cycle.py` per popolare il DB.")
    st.stop()

# ----------------------------------------------------------------------------
# Date range picker
# ----------------------------------------------------------------------------

st.sidebar.header("Periodo")
today = date.today()
default_from = today - timedelta(days=6)
default_to = today

range_input = st.sidebar.date_input(
    "Da → A",
    value=(default_from, default_to),
    max_value=today,
)
if isinstance(range_input, tuple) and len(range_input) == 2:
    date_from, date_to = range_input
else:
    date_from, date_to = default_from, default_to

# Comode quick selections
quick = st.sidebar.radio(
    "Quick",
    ["Custom (sopra)", "Oggi", "Ieri", "Ultimi 7 gg",
     "Ultimi 30 gg", "Questo mese", "Tutto"],
    index=0,
)
if quick == "Oggi":
    date_from = date_to = today
elif quick == "Ieri":
    date_from = date_to = today - timedelta(days=1)
elif quick == "Ultimi 7 gg":
    date_from, date_to = today - timedelta(days=6), today
elif quick == "Ultimi 30 gg":
    date_from, date_to = today - timedelta(days=29), today
elif quick == "Questo mese":
    date_from = today.replace(day=1)
    date_to = today
elif quick == "Tutto":
    if not listings.empty and listings["first_seen_at"].notna().any():
        date_from = listings["first_seen_at"].min().date()
    date_to = today

# Datetime aware
dt_from = pd.Timestamp(date_from, tz="UTC")
dt_to = pd.Timestamp(date_to, tz="UTC") + pd.Timedelta(days=1)
range_days = max(1, (date_to - date_from).days + 1)

# Periodo precedente identico (per delta)
prev_from = dt_from - pd.Timedelta(days=range_days)
prev_to = dt_from

st.sidebar.divider()
st.sidebar.markdown(f"**Periodo**: {date_from} → {date_to} ({range_days} gg)")
st.sidebar.markdown(f"**Confronto**: {prev_from.date()} → {(prev_to - pd.Timedelta(days=1)).date()}")

# ----------------------------------------------------------------------------
# Subsetting
# ----------------------------------------------------------------------------

period = listings[
    (listings["first_seen_at"] >= dt_from)
    & (listings["first_seen_at"] < dt_to)
]
prev_period = listings[
    (listings["first_seen_at"] >= prev_from)
    & (listings["first_seen_at"] < prev_to)
]

period_priv = period[period["advertiser_type"] == "private"]
prev_priv = prev_period[prev_period["advertiser_type"] == "private"]


def delta_pct(curr: int, prev: int) -> str | None:
    if prev == 0 and curr == 0:
        return None
    if prev == 0:
        return f"+{curr}"
    pct = (curr - prev) / prev * 100
    return f"{pct:+.0f}%"


# ----------------------------------------------------------------------------
# KPI ROW con delta vs periodo precedente
# ----------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    "Nuovi annunci",
    f"{len(period):,}",
    delta=delta_pct(len(period), len(prev_period)),
)
c2.metric(
    "Nuovi PRIVATI",
    f"{len(period_priv):,}",
    delta=delta_pct(len(period_priv), len(prev_priv)),
    help="L'obiettivo del bot",
)
c3.metric(
    "Idealista",
    f"{len(period[period['portal'] == 'idealista']):,}",
    delta=delta_pct(
        len(period[period["portal"] == "idealista"]),
        len(prev_period[prev_period["portal"] == "idealista"]),
    ),
)
c4.metric(
    "Immobiliare",
    f"{len(period[period['portal'] == 'immobiliare']):,}",
    delta=delta_pct(
        len(period[period["portal"] == "immobiliare"]),
        len(prev_period[prev_period["portal"] == "immobiliare"]),
    ),
)
priv_pct = len(period_priv) / max(1, len(period)) * 100
prev_priv_pct = len(prev_priv) / max(1, len(prev_period)) * 100
c5.metric(
    "% Privati",
    f"{priv_pct:.1f}%",
    delta=f"{priv_pct - prev_priv_pct:+.1f} pp" if prev_period.shape[0] else None,
)

st.divider()

# ----------------------------------------------------------------------------
# Trend giornaliero
# ----------------------------------------------------------------------------

if period.empty:
    st.info("Nessun annuncio nel periodo selezionato.")
    st.stop()

g1, g2 = st.columns(2)

with g1:
    st.subheader("Trend nuovi annunci per giorno")
    by_day = (
        period.assign(day=period["first_seen_at"].dt.date)
        .groupby(["day", "portal"])
        .size()
        .reset_index(name="annunci")
    )
    fig = px.line(
        by_day, x="day", y="annunci", color="portal", markers=True,
        color_discrete_map={"idealista": "#2E7D32", "immobiliare": "#1976D2"},
    )
    fig.update_layout(height=350, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with g2:
    st.subheader("Trend nuovi PRIVATI per giorno")
    by_day_priv = (
        period_priv.assign(day=period_priv["first_seen_at"].dt.date)
        .groupby(["day", "portal"])
        .size()
        .reset_index(name="annunci")
    )
    if by_day_priv.empty:
        st.info("Nessun nuovo privato nel periodo")
    else:
        fig = px.bar(
            by_day_priv, x="day", y="annunci", color="portal",
            text="annunci", barmode="group",
            color_discrete_map={"idealista": "#2E7D32", "immobiliare": "#1976D2"},
        )
        fig.update_layout(height=350, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------
# Top 10 zone privati + heatmap giorno×ora
# ----------------------------------------------------------------------------

g3, g4 = st.columns(2)

with g3:
    st.subheader("Top 10 zone con privati (nel periodo)")
    tz = (
        period_priv[
            period_priv["microzone"].notna() & (period_priv["microzone"] != "")
        ]
        .groupby("microzone")
        .size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
        .head(10)
    )
    if tz.empty:
        st.info("Nessun privato nel periodo")
    else:
        fig = px.bar(
            tz, x="n", y="microzone", orientation="h",
            color_discrete_sequence=["#FF6F00"], text="n",
        )
        fig.update_layout(
            height=380, margin=dict(t=10, l=0, r=0, b=0),
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(fig, use_container_width=True)

with g4:
    st.subheader("Heatmap pubblicazione (giorno × ora)")
    if range_days < 3:
        st.info("Range troppo corto — seleziona almeno 3 giorni")
    else:
        df = period.copy()
        df["weekday"] = df["first_seen_at"].dt.day_name()
        df["hour"] = df["first_seen_at"].dt.hour
        wd_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]
        heat = (
            df.groupby(["weekday", "hour"])
            .size()
            .reset_index(name="n")
            .pivot(index="weekday", columns="hour", values="n")
            .reindex(wd_order)
            .fillna(0)
        )
        if heat.empty:
            st.info("Pochi dati")
        else:
            fig = px.imshow(
                heat, color_continuous_scale="Greens",
                aspect="auto", labels={"color": "annunci"},
            )
            fig.update_layout(height=380, margin=dict(t=10, l=0, r=0, b=0))
            st.plotly_chart(fig, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Conversione: annunci → privati → con phone → contattati
# ----------------------------------------------------------------------------

st.subheader("🔄 Funnel di conversione nel periodo")

n_listings = len(period)
n_priv_listings = len(period_priv)

# Privati con phone (via contatti collegati ai listing del periodo)
contacts_priv_with_phone = 0
contacted = 0
if not contacts.empty and not period_priv.empty:
    # Trovo contact_id collegati ai listings nel periodo (richiede lc, semplifico
    # contando i contatti privati con first_seen_at nel periodo)
    cph = contacts[
        (contacts["kind"] == "private")
        & contacts["phone_e164"].notna()
        & (contacts["first_seen_at"] >= dt_from)
        & (contacts["first_seen_at"] < dt_to)
    ]
    contacts_priv_with_phone = len(cph)

    if not outreach.empty:
        sent_in_period = outreach[
            outreach["status"].isin(["sent", "delivered", "replied"])
            & (outreach["queued_at"] >= dt_from)
            & (outreach["queued_at"] < dt_to)
        ]
        contacted = len(sent_in_period)

funnel = pd.DataFrame({
    "stage": [
        "Annunci totali",
        "Solo PRIVATI",
        "Con telefono (contattabili)",
        "Effettivamente contattati",
    ],
    "n": [n_listings, n_priv_listings, contacts_priv_with_phone, contacted],
})
fig = go.Figure(go.Funnel(
    y=funnel["stage"], x=funnel["n"], textinfo="value+percent initial",
    marker={"color": ["#90A4AE", "#2E7D32", "#FF6F00", "#D32F2F"]},
))
fig.update_layout(height=380, margin=dict(t=10, l=0, r=0, b=0))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Tabella riepilogo giornaliera
# ----------------------------------------------------------------------------

st.subheader("📅 Riepilogo giornaliero")
df = period.copy()
df["day"] = df["first_seen_at"].dt.date
df["is_priv"] = (df["advertiser_type"] == "private").astype(int)
df["is_ide"] = (df["portal"] == "idealista").astype(int)
df["is_imm"] = (df["portal"] == "immobiliare").astype(int)
df["ide_priv"] = (df["is_ide"] & df["is_priv"]).astype(int)
df["imm_priv"] = (df["is_imm"] & df["is_priv"]).astype(int)

daily = (
    df.groupby("day")
    .agg(
        annunci=("id", "count"),
        privati=("is_priv", "sum"),
        idealista=("is_ide", "sum"),
        immobiliare=("is_imm", "sum"),
        idealista_privati=("ide_priv", "sum"),
        immobiliare_privati=("imm_priv", "sum"),
        prezzo_medio=("price_eur", "mean"),
    )
    .reset_index()
    .sort_values("day", ascending=False)
)

if not daily.empty:
    daily["prezzo_medio"] = daily["prezzo_medio"].round(0)
    # Percentuali "privati su totale portale" per giorno
    daily["perc_idealista_privati"] = (
        daily["idealista_privati"] / daily["idealista"].replace(0, pd.NA) * 100
    ).round(1)
    daily["perc_immobiliare_privati"] = (
        daily["immobiliare_privati"] / daily["immobiliare"].replace(0, pd.NA) * 100
    ).round(1)

    daily = daily[[
        "day", "annunci", "privati",
        "idealista", "idealista_privati", "perc_idealista_privati",
        "immobiliare", "immobiliare_privati", "perc_immobiliare_privati",
        "prezzo_medio",
    ]]

    st.dataframe(
        daily, hide_index=True, use_container_width=True,
        column_config={
            "day": st.column_config.DateColumn("Giorno", format="DD/MM/YYYY"),
            "annunci": st.column_config.NumberColumn("Tot"),
            "privati": st.column_config.NumberColumn("Privati"),
            "idealista": st.column_config.NumberColumn("Idealista"),
            "idealista_privati": st.column_config.NumberColumn("Ide priv."),
            "perc_idealista_privati": st.column_config.NumberColumn(
                "% priv Ide", format="%.1f%%",
                help="Quota privati sul totale Idealista del giorno",
            ),
            "immobiliare": st.column_config.NumberColumn("Immo"),
            "immobiliare_privati": st.column_config.NumberColumn("Immo priv."),
            "perc_immobiliare_privati": st.column_config.NumberColumn(
                "% priv Immo", format="%.1f%%",
                help="Quota privati sul totale Immobiliare del giorno",
            ),
            "prezzo_medio": st.column_config.NumberColumn("€ medio", format="€ %d"),
        },
    )
