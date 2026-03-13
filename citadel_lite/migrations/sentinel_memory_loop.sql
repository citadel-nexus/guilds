-- ============================================================
-- Sentinel Memory Loop — Supabase Tables
-- SRS: SRS-SENTINEL-MEMORY-001 / 002 / 003
-- Apply via: Supabase Dashboard → SQL Editor → Run
-- ============================================================

-- Context cache: what pre-call reads on every call start
CREATE TABLE IF NOT EXISTS public.sentinel_context_cache (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_id             TEXT UNIQUE NOT NULL,
    is_returning          BOOLEAN DEFAULT true,
    call_count            INTEGER DEFAULT 0,
    last_conversation_id  TEXT,
    last_call_date        TIMESTAMPTZ,
    relationship_summary  TEXT DEFAULT '',
    last_topics           TEXT DEFAULT '',
    open_items            TEXT DEFAULT '',
    sentiment_trend       TEXT DEFAULT 'warm',
    emotional_tone        TEXT DEFAULT 'warm',
    recommended_action    TEXT DEFAULT '',
    conversation_style    TEXT DEFAULT 'direct',
    promises_ledger       TEXT DEFAULT '',
    updated_at            TIMESTAMPTZ DEFAULT now(),
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentinel_cache_caller
    ON public.sentinel_context_cache(caller_id);

-- Enable RLS
ALTER TABLE public.sentinel_context_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on sentinel_context_cache"
    ON public.sentinel_context_cache
    FOR ALL
    USING (auth.role() = 'service_role');


-- Promises ledger
CREATE TABLE IF NOT EXISTS public.sentinel_promises (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id           TEXT NOT NULL,
    caller_id                 TEXT NOT NULL,
    text                      TEXT NOT NULL,
    owner                     TEXT NOT NULL CHECK (owner IN ('human', 'sentinel')),
    status                    TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'resolved', 'broken', 'expired')),
    context                   TEXT DEFAULT '',
    resolution                TEXT DEFAULT '',
    resolved_at               TIMESTAMPTZ,
    resolved_conversation_id  TEXT,
    created_at                TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentinel_promises_caller
    ON public.sentinel_promises(caller_id, status);
CREATE INDEX IF NOT EXISTS idx_sentinel_promises_active
    ON public.sentinel_promises(status) WHERE status = 'active';

ALTER TABLE public.sentinel_promises ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on sentinel_promises"
    ON public.sentinel_promises
    FOR ALL
    USING (auth.role() = 'service_role');


-- Post-call audit log
CREATE TABLE IF NOT EXISTS public.sentinel_post_call_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id         TEXT NOT NULL,
    caller_id               TEXT NOT NULL,
    call_duration_secs      FLOAT,
    memories_stored         INTEGER DEFAULT 0,
    promises_created        INTEGER DEFAULT 0,
    promises_resolved       INTEGER DEFAULT 0,
    sentiment               TEXT,
    growth_note_stored      BOOLEAN DEFAULT false,
    emotional_shift_stored  BOOLEAN DEFAULT false,
    processing_agent        TEXT DEFAULT 'sentinel',
    created_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentinel_postcall_conv
    ON public.sentinel_post_call_log(conversation_id);
CREATE INDEX IF NOT EXISTS idx_sentinel_postcall_caller
    ON public.sentinel_post_call_log(caller_id);

ALTER TABLE public.sentinel_post_call_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on sentinel_post_call_log"
    ON public.sentinel_post_call_log
    FOR ALL
    USING (auth.role() = 'service_role');


-- Pre-call audit log
CREATE TABLE IF NOT EXISTS public.sentinel_pre_call_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   TEXT NOT NULL,
    caller_id         TEXT NOT NULL,
    is_returning      BOOLEAN DEFAULT false,
    cache_hit         BOOLEAN DEFAULT false,
    call_count        INTEGER DEFAULT 0,
    fragments_seeded  INTEGER DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentinel_precall_conv
    ON public.sentinel_pre_call_log(conversation_id);

ALTER TABLE public.sentinel_pre_call_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on sentinel_pre_call_log"
    ON public.sentinel_pre_call_log
    FOR ALL
    USING (auth.role() = 'service_role');


-- API keys table (for MCP server auth verification)
CREATE TABLE IF NOT EXISTS public.api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    key_hash    TEXT UNIQUE NOT NULL,
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now(),
    last_used   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash
    ON public.api_keys(key_hash) WHERE active = true;

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on api_keys"
    ON public.api_keys
    FOR ALL
    USING (auth.role() = 'service_role');


-- ── Useful views ─────────────────────────────────────────────────────────────

-- Active promises by caller (used by dashboard)
CREATE OR REPLACE VIEW public.sentinel_active_promises AS
SELECT
    caller_id,
    COUNT(*) AS active_count,
    MAX(created_at) AS latest_promise_date
FROM public.sentinel_promises
WHERE status = 'active'
GROUP BY caller_id;

-- Memory stats by caller
CREATE OR REPLACE VIEW public.sentinel_caller_stats AS
SELECT
    c.caller_id,
    c.call_count,
    c.last_call_date,
    c.emotional_tone,
    c.conversation_style,
    COALESCE(p.active_count, 0) AS active_promises,
    c.updated_at
FROM public.sentinel_context_cache c
LEFT JOIN public.sentinel_active_promises p USING (caller_id)
ORDER BY c.updated_at DESC;
