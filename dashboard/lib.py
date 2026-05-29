"""Funzioni condivise tra le pagine della dashboard.

Caching:
  - @st.cache_resource: il client Supabase (single connection)
  - @st.cache_data(ttl=60): le query di sola lettura (refresh ogni 60s)

Le mutazioni (mark_opted_out, ecc.) sono fuori cache.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

# Permette `from src...` quando si lancia da dashboard/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


# ============================================================================
# Config lookup: env-var prima (locale), poi st.secrets (Streamlit Cloud)
# ============================================================================

def get_config(key: str, default: str | None = None) -> str | None:
    """Cerca la config in: os.environ → st.secrets → default.

    Su Streamlit Community Cloud non c'è .env; le credenziali vivono in
    `st.secrets` (impostate dalla UI Settings → Secrets).
    """
    val = os.environ.get(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except (FileNotFoundError, AttributeError):
        pass
    return default


# ============================================================================
# Auth basic via DASHBOARD_PASSWORD (se non settata, no auth)
# ============================================================================

def require_auth() -> None:
    pw = get_config("DASHBOARD_PASSWORD")
    if not pw:
        return  # auth disabilitata
    if st.session_state.get("auth_ok"):
        return
    st.title("🔒 Login")
    inp = st.text_input("Password", type="password")
    if st.button("Entra"):
        if inp == pw:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()


# ============================================================================
# Supabase client
# ============================================================================

@st.cache_resource
def sb() -> Client:
    url = get_config("SUPABASE_URL")
    key = get_config("SUPABASE_SERVICE_KEY")
    if not url or not key:
        st.error(
            "Manca la configurazione Supabase. Setta `SUPABASE_URL` e "
            "`SUPABASE_SERVICE_KEY` in .env (locale) o Secrets (Cloud)."
        )
        st.stop()
    return create_client(url, key)


# ============================================================================
# Read queries cached
# ============================================================================

@st.cache_data(ttl=60)
def get_listings_df() -> pd.DataFrame:
    rows = sb().table("listings").select("*").execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("first_seen_at", "last_seen_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


@st.cache_data(ttl=60)
def get_contacts_df() -> pd.DataFrame:
    rows = sb().table("contacts").select("*").execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("first_seen_at", "last_seen_at", "opted_out_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


@st.cache_data(ttl=60)
def get_outreach_df() -> pd.DataFrame:
    rows = sb().table("outreach_log").select("*").execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("queued_at", "sent_at", "responded_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


@st.cache_data(ttl=60)
def get_listing_contacts_df() -> pd.DataFrame:
    rows = sb().table("listing_contacts").select("*").execute().data
    return pd.DataFrame(rows)


def clear_caches() -> None:
    """Da chiamare dopo una mutation."""
    get_listings_df.clear()
    get_contacts_df.clear()
    get_outreach_df.clear()
    get_listing_contacts_df.clear()


# ============================================================================
# UI helpers
# ============================================================================

def kpi(col, label: str, value, delta: str | None = None, help: str | None = None):
    col.metric(label, value, delta, help=help)


def setup_page(title: str, icon: str = "🏠") -> None:
    st.set_page_config(
        page_title=f"BOT_IMMOBILIARE — {title}",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    require_auth()


# ============================================================================
# Helpers per link Chiama / WhatsApp / Share
# ============================================================================

def call_url(phone_e164: str | None) -> str | None:
    """tel: link cliccabile su mobile."""
    if not phone_e164:
        return None
    return f"tel:{phone_e164}"


def whatsapp_url(phone_e164: str | None, message: str | None = None) -> str | None:
    """wa.me link con messaggio precompilato (URL-encoded)."""
    if not phone_e164:
        return None
    # wa.me vuole il numero senza '+'
    num = phone_e164.lstrip("+")
    url = f"https://wa.me/{num}"
    if message:
        from urllib.parse import quote
        url += f"?text={quote(message)}"
    return url


def telegram_share_url(text: str, url: str | None = None) -> str:
    """Share intent Telegram (utile per inoltrarti i lead in chat)."""
    from urllib.parse import quote
    if url:
        return f"https://t.me/share/url?url={quote(url)}&text={quote(text)}"
    return f"https://t.me/share/url?text={quote(text)}"


def listing_link(url: str | None) -> str:
    return url or "#"
