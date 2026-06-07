-- Aggiunta colonna data di pubblicazione dell'annuncio sul portale
-- (DIVERSA da first_seen_at che è quando il BOT l'ha visto la prima volta).
alter table listings
  add column if not exists published_at timestamptz;

create index if not exists listings_published_at_idx
    on listings(published_at desc nulls last);
