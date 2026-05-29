-- ============================================================================
-- BOT_IMMOBILIARE — schema iniziale
--
-- Modello di dedup multi-livello:
--   1) listings   uniche per (portal, external_id)  → re-scrape = update, no dup
--   2) contacts   uniche per phone_e164 oppure email → stessa persona su
--                 più annunci = 1 solo record
--   3) outreach_log: prima di inviare, applicazione filtra contact_id già
--                    contattati su quel canale + opted_out_at not null
--   4) portal_accounts: rotation + cooldown per non bruciare gli account
--
-- Tutto IF NOT EXISTS → riapplicabile.
-- ============================================================================

-- ---------- LISTINGS ----------
create table if not exists listings (
  id              bigint generated always as identity primary key,
  portal          text   not null,
  external_id     text   not null,
  url             text   not null,

  title           text,
  description     text,
  price_eur       int,
  surface_m2      int,
  rooms           text,
  bathrooms       text,
  floor           text,
  typology        text,

  address         text,
  city            text,
  macrozone       text,
  microzone       text,
  latitude        double precision,
  longitude       double precision,

  advertiser_type text,                                    -- 'agency' | 'private'
  advertiser_name text,
  visibility      text,
  contract        text,

  raw_data        jsonb,                                   -- payload originale

  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  scraped_count   int         not null default 1,
  status          text        not null default 'active',  -- active|removed|filtered

  constraint listings_portal_external_id_uk unique (portal, external_id)
);

create index if not exists listings_portal_advtype_idx
    on listings(portal, advertiser_type);
create index if not exists listings_first_seen_idx
    on listings(first_seen_at desc);
create index if not exists listings_city_zone_idx
    on listings(city, macrozone);

-- ---------- CONTACTS ----------
-- Un contatto = una persona (proprietario o agente). Dedup su phone_e164
-- (normalizzato in formato +39…) oppure su email lower.
create table if not exists contacts (
  id              bigint generated always as identity primary key,
  phone_e164      text unique,            -- es. '+393331234567'
  email           text unique,            -- lowercased
  display_name    text,
  kind            text,                   -- 'private' | 'agency'
  source          text,                   -- 'advertiser' | 'text' | 'reveal' | 'form'

  opted_out_at    timestamptz,            -- impostato quando rispondono STOP / opt-out
  do_not_contact  boolean not null default false,
  notes           text,

  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),

  -- vincolo: almeno uno tra phone ed email deve esserci
  constraint contacts_has_identifier check (
    phone_e164 is not null or email is not null
  )
);

create index if not exists contacts_opted_out_idx
    on contacts(opted_out_at) where opted_out_at is not null;

-- ---------- LISTING ↔ CONTACT (N:M) ----------
create table if not exists listing_contacts (
  listing_id  bigint not null references listings(id) on delete cascade,
  contact_id  bigint not null references contacts(id) on delete cascade,
  role        text   not null default 'advertiser',  -- advertiser|agency|owner
  created_at  timestamptz not null default now(),
  primary key (listing_id, contact_id, role)
);

create index if not exists listing_contacts_contact_idx
    on listing_contacts(contact_id);

-- ---------- OUTREACH LOG ----------
-- Una riga per ogni messaggio (preparato/inviato/fallito).
-- Prima di inviare, l'app verifica:
--   * contacts.opted_out_at IS NULL AND do_not_contact = false
--   * non esiste già una riga per (contact_id, channel) con status
--     IN ('queued','sent','delivered','replied') negli ultimi 90 gg
create table if not exists outreach_log (
  id              bigint generated always as identity primary key,
  contact_id      bigint not null references contacts(id),
  listing_id      bigint           references listings(id),  -- annuncio che ha motivato il contatto (nullable se l'annuncio sparisce)
  channel         text   not null,                           -- 'sms' | 'email' | 'portal_form' | 'whatsapp'
  status          text   not null,                           -- queued|sent|delivered|failed|replied|opted_out
  template_id     text,
  message         text,                                      -- testo effettivo inviato
  provider_id     text,                                      -- twilio sid / form receipt id
  error           text,
  queued_at       timestamptz not null default now(),
  sent_at         timestamptz,
  responded_at    timestamptz,
  response_text   text
);

create index if not exists outreach_log_contact_channel_idx
    on outreach_log(contact_id, channel, status);
create index if not exists outreach_log_sent_at_idx
    on outreach_log(sent_at desc);

-- ---------- PORTAL ACCOUNTS ----------
-- Pool di account burner per reveal numero e invio form.
-- Reset reveals_today via cron giornaliero (o lazy on read).
create table if not exists portal_accounts (
  id              bigint generated always as identity primary key,
  portal          text not null,
  email           text not null,
  password_enc    text not null,            -- per ora plaintext, da cifrare prima di prod serio
  status          text not null default 'active',   -- active|cooldown|banned
  reveals_today   int  not null default 0,
  reveals_total   int  not null default 0,
  forms_today     int  not null default 0,
  forms_total     int  not null default 0,
  last_used_at    timestamptz,
  cooldown_until  timestamptz,
  notes           text,
  created_at      timestamptz not null default now(),
  constraint portal_accounts_portal_email_uk unique (portal, email)
);
