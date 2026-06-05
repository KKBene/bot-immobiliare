-- Aggiunta colonne spese condominiali e totale al listings.
alter table listings
  add column if not exists expenses_eur int,
  add column if not exists total_eur    int;

-- Indice utile per filtri tipici (prezzo totale)
create index if not exists listings_total_eur_idx on listings(total_eur);
