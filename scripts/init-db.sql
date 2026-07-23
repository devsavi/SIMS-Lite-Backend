-- =============================================================================
-- SIMS Lite — PostgreSQL initialisation script
-- Runs once when the postgres container first starts.
-- =============================================================================

-- Ensure the database exists (Docker creates it via POSTGRES_DB, but be safe)
SELECT 'CREATE DATABASE sims_lite'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'sims_lite'
)\gexec

-- Extensions useful for SIMS
\connect sims_lite

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- trigram similarity search
CREATE EXTENSION IF NOT EXISTS "unaccent";      -- accent-insensitive search
