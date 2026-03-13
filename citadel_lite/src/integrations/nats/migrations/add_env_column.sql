-- Migration: add_env_column.sql
-- Adds the `env` column to vcc_loop_state for environment tagging.
-- Run once per Supabase project.
--
-- Context: This column allows Citadel Lite to tag loop state rows with
--          the deployment environment (production / staging / local).
--          Loop orchestrator rows (loop_source='orchestrator') use this
--          to distinguish ECS vs VPS vs local runs.
--
-- Usage:
--   psql $DATABASE_URL -f add_env_column.sql
--   OR via Supabase Dashboard > SQL Editor

BEGIN;

ALTER TABLE public.vcc_loop_state
  ADD COLUMN IF NOT EXISTS env text DEFAULT 'local';

COMMENT ON COLUMN public.vcc_loop_state.env IS
  'Deployment environment tag: production | staging | local';

-- Index for filtering by environment
CREATE INDEX IF NOT EXISTS idx_vcc_loop_state_env
  ON public.vcc_loop_state (env);

COMMIT;
