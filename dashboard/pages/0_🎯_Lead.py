"""Pagina 'Lead da contattare' — la più importante per l'operatività.

Solo PRIVATI con telefono, ordinati per data, con:
  - link cliccabile Chiama (tel:) + WhatsApp (wa.me con msg precompilato)
  - bottone Telegram-share per inoltrarti il lead nella chat del bot
  - export CSV/vCard
  - filtri zona, prezzo, rooms
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from lib import (  # noqa: E402
    call_url,
    clear_caches,
    get_contacts_df,
    get_listing_contacts_df,
    get_listings_df,
    sb,
    setup_page,
    telegram_share_url,
    whatsapp_url,
)

setup_page("Lead", icon="🎯")
st.title("🎯 Lead da contattare")
st.caption(
    "Privati con telefono · ordinati per più recenti · click su 📞 / 💬 per agire"
)

# ----------------------------------------------------------------------------
# Carica + join
# ----------------------------------------------------------------------------

contacts = get_contacts_df()
listings = get_listings_df()
lc = get_listing_contacts_df()

if contacts.empty or listings.empty or lc.empty:
    st.warning("Niente lead ancora — esegui un cycle prima.")
    st.stop()

# Filtro: solo private, con phone, contattabili
priv = contacts[
    (contacts["kind"] == "private")
    & contacts["phone_e164"].notna()
    & contacts["opted_out_at"].isna()
    & (contacts["do_not_contact"] != True)
].copy()

# Per ogni contact, prendi l'annuncio più recente collegato
if not priv.empty and not lc.empty:
    listing_for_contact = (
        lc.merge(listings, left_on="listing_id", right_on="id")
        .sort_values("first_seen_at", ascending=False)
        .groupby("contact_id")
        .head(1)
        [["contact_id", "url", "title", "price_eur", "surface_m2",
          "rooms", "microzone", "portal", "advertiser_name", "first_seen_at"]]
    )
    priv = priv.merge(
        listing_for_contact, left_on="id", right_on="contact_id",
        how="left", suffixes=("", "_listing"),
    )

# ----------------------------------------------------------------------------
# Sidebar filtri
# ----------------------------------------------------------------------------

st.sidebar.header("Filtri lead")

# Zona
zones = sorted([z for z in priv["microzone"].dropna().unique() if z])
sel_zones = st.sidebar.multiselect("Zona", zones)

# Prezzo
prices = priv["price_eur"].dropna()
if not prices.empty:
    pmin, pmax = int(prices.min()), int(prices.max())
    price_range = st.sidebar.slider("Prezzo €/mese", pmin, pmax,
                                     (pmin, pmax))
else:
    price_range = None

# Solo non ancora contattati
only_uncontacted = st.sidebar.checkbox(
    "Solo non contattati", value=True,
    help="Esclude chi è già in outreach_log con status 'sent'/'delivered'",
)

# Apply
filt = priv.copy()
if sel_zones:
    filt = filt[filt["microzone"].isin(sel_zones)]
if price_range and not filt.empty:
    pmin, pmax = price_range
    filt = filt[(filt["price_eur"].isna())
                | ((filt["price_eur"] >= pmin) & (filt["price_eur"] <= pmax))]

if only_uncontacted:
    sb_client = sb()
    contacted = (
        sb_client.table("outreach_log")
        .select("contact_id")
        .in_("status", ["sent", "delivered", "replied"])
        .execute()
    )
    contacted_ids = {r["contact_id"] for r in contacted.data}
    if contacted_ids:
        filt = filt[~filt["id"].isin(contacted_ids)]

st.caption(f"**{len(filt)}** lead visibili (di {len(priv)} privati totali con telefono)")

# ----------------------------------------------------------------------------
# Render lead come "schede" con bottoni
# ----------------------------------------------------------------------------

if filt.empty:
    st.info("Nessun lead corrisponde ai filtri.")
    st.stop()

filt = filt.sort_values("first_seen_at", ascending=False).head(50)

template_msg = (
    "Ciao {name}, ho visto il tuo annuncio in {zone} su {portal}. "
    "Mi occupo di gestione affitti a medio termine a Milano: "
    "canone +30%, contratti 1-12 mesi, gestione totale. "
    "Se ti interessa una valutazione gratuita scrivimi. Paolo Vailati."
)

for _, row in filt.iterrows():
    name = row.get("display_name") or row.get("advertiser_name") or "?"
    first_name = name.split()[0] if name and name != "?" else ""
    zone = row.get("microzone") or "Milano"
    portal = (row.get("portal") or "").title() or "portale"
    phone = row["phone_e164"]
    listing_url = row.get("url") or ""
    msg = template_msg.format(name=first_name, zone=zone, portal=portal)

    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f"### 👤 {name}")
            specs = []
            if pd.notna(row.get("price_eur")):
                specs.append(f"💰 {int(row['price_eur'])} €/mese")
            if pd.notna(row.get("surface_m2")):
                specs.append(f"📐 {int(row['surface_m2'])} m²")
            if row.get("rooms"):
                specs.append(f"🚪 {row['rooms']} locali")
            if specs:
                st.markdown("  ·  ".join(specs))
            st.markdown(f"📍 **{zone}** · `{phone}`")
            if listing_url:
                st.markdown(f"🔗 [Apri annuncio su {portal}]({listing_url})")
            ts = pd.Timestamp(row.get("first_seen_at")).strftime("%d/%m %H:%M") \
                if pd.notna(row.get("first_seen_at")) else "?"
            st.caption(f"Visto: {ts}")

        with c2:
            st.link_button(
                f"📞 Chiama {phone}",
                call_url(phone),
                use_container_width=True,
            )
            st.link_button(
                "💬 WhatsApp con messaggio",
                whatsapp_url(phone, msg) or "#",
                use_container_width=True,
            )
            st.link_button(
                "✈️ Inoltra lead a Telegram",
                telegram_share_url(
                    f"{name} ({phone}) — {zone}, {portal}",
                    listing_url,
                ),
                use_container_width=True,
            )
            cid = int(row["id"])
            if st.button("🚫 Marca opt-out", key=f"opt_{cid}",
                         use_container_width=True):
                from datetime import datetime, timezone as tz
                sb().table("contacts").update(
                    {"opted_out_at": datetime.now(tz.utc).isoformat()}
                ).eq("id", cid).execute()
                clear_caches()
                st.rerun()

st.divider()

# Export CSV / vCard
exp_cols = ["display_name", "phone_e164", "microzone", "price_eur",
            "surface_m2", "rooms", "url"]
exp_cols = [c for c in exp_cols if c in filt.columns]
csv = filt[exp_cols].to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Esporta CSV", csv, "lead_export.csv", mime="text/csv")


def to_vcard(df: pd.DataFrame) -> bytes:
    cards = []
    for _, r in df.iterrows():
        name = r.get("display_name") or "Lead"
        phone = r["phone_e164"]
        note = (f"Annuncio: {r.get('url') or ''} · Zona: {r.get('microzone') or ''}"
                f" · {r.get('price_eur') or '?'}€/mese")
        cards.append(
            "BEGIN:VCARD\nVERSION:3.0\n"
            f"FN:{name}\n"
            f"TEL;TYPE=CELL:{phone}\n"
            f"NOTE:{note}\n"
            "END:VCARD\n"
        )
    return "".join(cards).encode("utf-8")


vcf = to_vcard(filt)
st.download_button(
    "📇 Esporta vCard (.vcf) — importa nei contatti del telefono",
    vcf, "leads.vcf", mime="text/vcard",
)
