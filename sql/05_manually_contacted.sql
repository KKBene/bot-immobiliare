-- Backup persistente dei Contattato="Sì" del foglio Google.
--
-- Strategy: prima di ogni sync, il bot legge il CSV pubblico del foglio
-- e segna manually_contacted_at sulle righe con Contattato='Sì'.
-- Quando il bot scrive di nuovo, popola Contattato dalla colonna del DB,
-- così:
--   - Se l'utente cancella la tab → i Sì ritornano al prossimo sync.
--   - Se l'utente toglie un Sì → al sync dopo viene riportato a "No" in DB.

alter table listings
  add column if not exists manually_contacted_at timestamptz;

create index if not exists listings_manually_contacted_idx
    on listings(manually_contacted_at)
    where manually_contacted_at is not null;
