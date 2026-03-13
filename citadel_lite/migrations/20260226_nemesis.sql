-- migrations/20260226_nemesis.sql
-- Nemesis L3/L4 schema: honeypot hits + threat events + classified threats

-- ── L3 Honeypot hits ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.nemesis_honeypot_hits (
    hit_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    path         text NOT NULL,
    client_ip    inet,
    method       text DEFAULT 'GET',
    threat_label text DEFAULT 'L3_HONEYPOT',
    timestamp    timestamptz NOT NULL DEFAULT now(),
    metadata     jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_nemesis_honeypot_hits_ip
    ON public.nemesis_honeypot_hits (client_ip);

CREATE INDEX IF NOT EXISTS idx_nemesis_honeypot_hits_ts
    ON public.nemesis_honeypot_hits (timestamp DESC);

COMMENT ON TABLE public.nemesis_honeypot_hits
    IS 'Nemesis L3 Hunter — decoy endpoint hit log';

-- ── L4 Threat events (raw classified events) ──────────────────────────────────

CREATE TABLE IF NOT EXISTS public.nemesis_events (
    event_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type   text NOT NULL,     -- 'l2_block' | 'l3_honeypot' | 'l4_oracle'
    source_ip    inet,
    threat_score float DEFAULT 0.0,
    threats      text[],            -- categories: sqli, xss, ssrf, prompt_injection
    path         text,
    method       text,
    payload_hash text,              -- SHA-256 of request body (PII-free)
    country_code text,
    timestamp    timestamptz NOT NULL DEFAULT now(),
    metadata     jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_nemesis_events_ts
    ON public.nemesis_events (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_nemesis_events_type
    ON public.nemesis_events (event_type);

CREATE INDEX IF NOT EXISTS idx_nemesis_events_ip
    ON public.nemesis_events (source_ip);

COMMENT ON TABLE public.nemesis_events
    IS 'Nemesis L4 Oracle — raw classified threat events';

-- ── L4 Aggregated threats (per-IP quarantine table) ───────────────────────────

CREATE TABLE IF NOT EXISTS public.nemesis_threats (
    threat_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_ip    inet NOT NULL UNIQUE,
    threat_score float DEFAULT 0.0,
    hit_count    int DEFAULT 1,
    categories   text[],
    quarantined  boolean DEFAULT false,
    quarantine_until timestamptz,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now(),
    country_code text,
    metadata     jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_nemesis_threats_ip
    ON public.nemesis_threats (source_ip);

CREATE INDEX IF NOT EXISTS idx_nemesis_threats_quarantined
    ON public.nemesis_threats (quarantined);

COMMENT ON TABLE public.nemesis_threats
    IS 'Nemesis L4 Oracle — per-IP aggregated threat state (quarantine registry)';
