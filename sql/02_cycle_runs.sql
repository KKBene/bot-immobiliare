-- ============================================================================
-- Tabella cycle_runs: history dei run del bot per audit + anomaly detection
--
-- Ogni run del master cycle scrive una riga con stats completi + errori.
-- Permette analisi posthoc, dashboard "Sistema", e rilevamento anomalie.
-- ============================================================================

create table if not exists cycle_runs (
  id              bigint generated always as identity primary key,
  started_at      timestamptz not null,
  finished_at     timestamptz,
  duration_s      double precision,
  stats           jsonb,                   -- portal_counts (synced_new, touched_existing, ...)
  errors          jsonb,                   -- list di stringhe
  anomalies       jsonb,                   -- list di {level, code, message}
  notified        boolean not null default false,
  created_at      timestamptz not null default now()
);

create index if not exists cycle_runs_started_at_idx
    on cycle_runs(started_at desc);
create index if not exists cycle_runs_anomalies_present_idx
    on cycle_runs ((jsonb_array_length(anomalies) > 0))
    where anomalies is not null;
