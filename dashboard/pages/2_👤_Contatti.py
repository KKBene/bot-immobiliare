"""Pagina Contatti: tabella + azioni rapide (opt-out, do-not-contact)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import (  # noqa: E402
    clear_caches,
    get_contacts_df,
    get_listing_contacts_df,
    get_listings_df,
    sb,
    setup_page,
)

setup_page("Contatti", icon="👤")
st.title("👤 Contatti")

contacts = get_contacts_df()
lc = get_listing_contacts_df()
listings = get_listings_df()

if contacts.empty:
    st.warning("Nessun contatto ancora.")
    st.stop()

# Numero annunci per contatto
if not lc.empty:
    n_per_contact = lc.groupby("contact_id").size().rename("n_annunci")
    contacts = contacts.merge(
        n_per_contact, left_on="id", right_index=True, how="left"
    )
    contacts["n_annunci"] = contacts["n_annunci"].fillna(0).astype(int)
else:
    contacts["n_annunci"] = 0

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------

st.sidebar.header("Filtri")

kinds = sorted(contacts["kind"].dropna().unique().tolist())
sel_kinds = st.sidebar.multiselect("Tipo", kinds, default=kinds)

only_with_phone = st.sidebar.checkbox("Solo con telefono", value=True)
only_contactable = st.sidebar.checkbox(
    "Escludi opt-out / DNC", value=True,
    help="Nasconde i contatti già opt-out o flaggati do_not_contact",
)

filt = contacts.copy()
if sel_kinds:
    filt = filt[filt["kind"].isin(sel_kinds)]
if only_with_phone:
    filt = filt[filt["phone_e164"].notna()]
if only_contactable:
    filt = filt[
        filt["opted_out_at"].isna() & (filt["do_not_contact"] != True)
    ]

st.caption(f"**{len(filt):,}** contatti visibili (di {len(contacts):,} totali)")

# ----------------------------------------------------------------------------
# Tabella
# ----------------------------------------------------------------------------

display_cols = [
    "id", "kind", "display_name",
    "phone_e164", "email",
    "n_annunci",
    "first_seen_at", "last_seen_at",
    "opted_out_at", "do_not_contact",
    "source",
]
display_cols = [c for c in display_cols if c in filt.columns]

st.dataframe(
    filt[display_cols].sort_values("last_seen_at", ascending=False),
    use_container_width=True,
    height=440,
    column_config={
        "id": st.column_config.NumberColumn("#"),
        "kind": st.column_config.TextColumn("Tipo"),
        "phone_e164": st.column_config.TextColumn("Telefono"),
        "n_annunci": st.column_config.NumberColumn("Annunci"),
        "first_seen_at": st.column_config.DatetimeColumn("Primo visto", format="DD/MM/YY HH:mm"),
        "last_seen_at": st.column_config.DatetimeColumn("Ultimo visto", format="DD/MM/YY HH:mm"),
        "opted_out_at": st.column_config.DatetimeColumn("Opt-out il", format="DD/MM/YY HH:mm"),
        "do_not_contact": st.column_config.CheckboxColumn("DNC"),
    },
    hide_index=True,
)

st.divider()

# ----------------------------------------------------------------------------
# Azione: opt-out / DNC manuale
# ----------------------------------------------------------------------------

st.subheader("Azioni manuali")

a1, a2 = st.columns(2)
with a1:
    target_id = st.number_input(
        "ID contatto", min_value=1, step=1,
        help="Copia l'# dalla tabella sopra"
    )
with a2:
    action = st.selectbox(
        "Azione",
        ["Mark opted-out", "Mark do-not-contact", "Rimuovi opt-out + DNC"],
    )

if st.button("Esegui", type="primary"):
    client = sb()
    if action == "Mark opted-out":
        client.table("contacts").update(
            {"opted_out_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", int(target_id)).execute()
        st.success(f"Contatto {target_id} opted-out")
    elif action == "Mark do-not-contact":
        client.table("contacts").update(
            {"do_not_contact": True}
        ).eq("id", int(target_id)).execute()
        st.success(f"Contatto {target_id} DNC=True")
    else:
        client.table("contacts").update(
            {"opted_out_at": None, "do_not_contact": False}
        ).eq("id", int(target_id)).execute()
        st.success(f"Contatto {target_id} riattivato")
    clear_caches()
    st.rerun()
