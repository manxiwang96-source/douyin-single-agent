-- Douyin worker business tables.
-- Do not ALTER LangGraph official checkpoints* / store tables.

CREATE TABLE IF NOT EXISTS app_users (
    user_id UUID PRIMARY KEY,
    login_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMPTZ NULL,
    CONSTRAINT app_users_status_chk CHECK (status IN ('active', 'disabled'))
);

CREATE TABLE IF NOT EXISTS app_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS app_sessions_user_id_idx ON app_sessions (user_id);

CREATE TABLE IF NOT EXISTS agent_instances (
    agent_instance_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    template_code TEXT NOT NULL,
    title TEXT NOT NULL,
    intro TEXT NOT NULL DEFAULT '',
    avatar_uri TEXT NULL,
    agent_mode TEXT NOT NULL DEFAULT 'single',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_instances_title_chk CHECK (
        title = btrim(title) AND title <> '' AND title !~ '\s'
    ),
    CONSTRAINT agent_instances_mode_chk CHECK (agent_mode IN ('single', 'multi')),
    CONSTRAINT agent_instances_status_chk CHECK (status IN ('draft', 'active', 'archived'))
);
CREATE INDEX IF NOT EXISTS agent_instances_user_id_idx ON agent_instances (user_id);
-- UNIQUE (user_id, lower(title)) WHERE status <> 'archived'
CREATE UNIQUE INDEX IF NOT EXISTS agent_instances_user_id_lower_title_active_uidx
    ON agent_instances (user_id, lower(title))
    WHERE status <> 'archived';

CREATE TABLE IF NOT EXISTS agent_instance_workflows (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    workflow_code TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_instance_workflows_instance_code_uidx UNIQUE (agent_instance_id, workflow_code)
);
CREATE INDEX IF NOT EXISTS agent_instance_workflows_user_id_idx ON agent_instance_workflows (user_id);
CREATE INDEX IF NOT EXISTS agent_instance_workflows_agent_instance_id_idx ON agent_instance_workflows (agent_instance_id);

CREATE TABLE IF NOT EXISTS app_threads (
    thread_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    title TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT app_threads_status_chk CHECK (status IN ('active', 'interrupted', 'closed', 'archived'))
);
CREATE INDEX IF NOT EXISTS app_threads_user_id_idx ON app_threads (user_id);
CREATE INDEX IF NOT EXISTS app_threads_agent_instance_id_idx ON app_threads (agent_instance_id);

CREATE TABLE IF NOT EXISTS douyin_accounts (
    account_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    account TEXT NOT NULL,
    display_name TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT douyin_accounts_status_chk CHECK (status IN ('active', 'paused', 'needs_login'))
);
CREATE INDEX IF NOT EXISTS douyin_accounts_user_id_idx ON douyin_accounts (user_id);
CREATE INDEX IF NOT EXISTS douyin_accounts_agent_instance_id_idx ON douyin_accounts (agent_instance_id);

CREATE TABLE IF NOT EXISTS job_definitions (
    job_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    kind TEXT NOT NULL,
    cron TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    enabled BOOLEAN NOT NULL DEFAULT true,
    require_approval BOOLEAN NOT NULL DEFAULT false,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS job_definitions_user_id_idx ON job_definitions (user_id);
CREATE INDEX IF NOT EXISTS job_definitions_agent_instance_id_idx ON job_definitions (agent_instance_id);

CREATE TABLE IF NOT EXISTS job_runs (
    job_run_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES job_definitions (job_id),
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    scheduled_for TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    error TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    CONSTRAINT job_runs_job_id_scheduled_for_uidx UNIQUE (job_id, scheduled_for),
    CONSTRAINT job_runs_status_chk CHECK (
        status IN (
            'scheduled',
            'running',
            'waiting_review',
            'sending',
            'succeeded',
            'failed',
            'skipped',
            'cancelled'
        )
    )
);
CREATE INDEX IF NOT EXISTS job_runs_user_id_idx ON job_runs (user_id);
CREATE INDEX IF NOT EXISTS job_runs_agent_instance_id_idx ON job_runs (agent_instance_id);
CREATE INDEX IF NOT EXISTS job_runs_job_id_idx ON job_runs (job_id);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    workflow_code TEXT NOT NULL,
    dify_app_id TEXT NULL,
    thread_id TEXT NULL,
    job_run_id UUID NULL REFERENCES job_runs (job_run_id),
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    outputs JSONB NULL,
    workflow_run_id TEXT NULL,
    status TEXT NOT NULL,
    error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_runs_status_chk CHECK (
        status IN ('running', 'succeeded', 'failed', 'timeout', 'auth_expired', 'cancelled')
    )
);
CREATE INDEX IF NOT EXISTS workflow_runs_user_id_idx ON workflow_runs (user_id);
CREATE INDEX IF NOT EXISTS workflow_runs_agent_instance_id_idx ON workflow_runs (agent_instance_id);
CREATE INDEX IF NOT EXISTS workflow_runs_job_run_id_idx ON workflow_runs (job_run_id);

CREATE TABLE IF NOT EXISTS engage_videos (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    job_run_id UUID NULL REFERENCES job_runs (job_run_id),
    thread_id TEXT NULL,
    workflow_run_id TEXT NULL,
    platform_video_id TEXT NOT NULL,
    keyword TEXT NULL,
    title TEXT NULL,
    url TEXT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT engage_videos_status_chk CHECK (
        status IN (
            'discovered',
            'selected',
            'scanning',
            'replying',
            'failed',
            'needs_login',
            'completed'
        )
    )
);
CREATE INDEX IF NOT EXISTS engage_videos_user_id_idx ON engage_videos (user_id);
CREATE INDEX IF NOT EXISTS engage_videos_agent_instance_id_idx ON engage_videos (agent_instance_id);

CREATE TABLE IF NOT EXISTS engage_comments (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    platform_comment_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    source_text TEXT NOT NULL DEFAULT '',
    score NUMERIC NULL,
    candidate_reply TEXT NULL,
    approved_reply TEXT NULL,
    require_approval BOOLEAN NOT NULL DEFAULT false,
    attempt_count INT NOT NULL DEFAULT 0,
    verify_result TEXT NULL,
    screenshot_uri TEXT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT engage_comments_status_chk CHECK (
        status IN (
            'proposed',
            'ready_to_send',
            'sending',
            'sent',
            'failed',
            'needs_login',
            'cancelled'
        )
    )
);
CREATE INDEX IF NOT EXISTS engage_comments_user_id_idx ON engage_comments (user_id);
CREATE INDEX IF NOT EXISTS engage_comments_agent_instance_id_idx ON engage_comments (agent_instance_id);

CREATE TABLE IF NOT EXISTS engage_dms (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    platform_message_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    source_text TEXT NOT NULL DEFAULT '',
    score NUMERIC NULL,
    candidate_reply TEXT NULL,
    approved_reply TEXT NULL,
    require_approval BOOLEAN NOT NULL DEFAULT false,
    attempt_count INT NOT NULL DEFAULT 0,
    verify_result TEXT NULL,
    screenshot_uri TEXT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT engage_dms_status_chk CHECK (
        status IN (
            'proposed',
            'ready_to_send',
            'sending',
            'sent',
            'failed',
            'needs_login',
            'cancelled'
        )
    )
);
CREATE INDEX IF NOT EXISTS engage_dms_user_id_idx ON engage_dms (user_id);
CREATE INDEX IF NOT EXISTS engage_dms_agent_instance_id_idx ON engage_dms (agent_instance_id);

CREATE TABLE IF NOT EXISTS media_assets (
    asset_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    thread_id TEXT NULL,
    kind TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    storage_status TEXT NOT NULL DEFAULT 'stored',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT media_assets_kind_chk CHECK (kind IN ('image', 'video')),
    CONSTRAINT media_assets_storage_status_chk CHECK (
        storage_status IN ('stored', 'offloaded', 'expired', 'missing')
    )
);
CREATE INDEX IF NOT EXISTS media_assets_user_id_idx ON media_assets (user_id);
CREATE INDEX IF NOT EXISTS media_assets_agent_instance_id_idx ON media_assets (agent_instance_id);

CREATE TABLE IF NOT EXISTS agent_knowledge_documents (
    document_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_knowledge_documents_source_chk CHECK (source IN ('seeded_demo', 'user_upload')),
    CONSTRAINT agent_knowledge_documents_status_chk CHECK (
        status IN ('uploaded', 'indexing', 'ready', 'failed', 'archived')
    )
);
CREATE INDEX IF NOT EXISTS agent_knowledge_documents_user_id_idx ON agent_knowledge_documents (user_id);
CREATE INDEX IF NOT EXISTS agent_knowledge_documents_agent_instance_id_idx ON agent_knowledge_documents (agent_instance_id);