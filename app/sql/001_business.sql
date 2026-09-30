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

CREATE TABLE IF NOT EXISTS skill_registry (
    skill_id UUID PRIMARY KEY,
    owner_scope TEXT NOT NULL,
    owner_user_id UUID NULL REFERENCES app_users (user_id),
    source_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    trigger_description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    source_uri TEXT NULL,
    source_ref TEXT NULL,
    content_digest TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    approval_mode TEXT NOT NULL,
    execution_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT skill_registry_owner_scope_chk CHECK (owner_scope IN ('platform', 'user')),
    CONSTRAINT skill_registry_owner_chk CHECK (
        (owner_scope = 'platform' AND owner_user_id IS NULL)
        OR (owner_scope = 'user' AND owner_user_id IS NOT NULL)
    ),
    CONSTRAINT skill_registry_source_type_chk CHECK (source_type IN ('builtin', 'custom', 'external')),
    CONSTRAINT skill_registry_risk_chk CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT skill_registry_approval_chk CHECK (approval_mode IN ('auto', 'once', 'session', 'always')),
    CONSTRAINT skill_registry_status_chk CHECK (status IN ('active', 'quarantined', 'archived', 'revoked'))
);
CREATE UNIQUE INDEX IF NOT EXISTS skill_registry_platform_code_uidx
    ON skill_registry (code) WHERE owner_scope = 'platform';
CREATE UNIQUE INDEX IF NOT EXISTS skill_registry_user_code_uidx
    ON skill_registry (owner_user_id, code) WHERE owner_scope = 'user';
CREATE INDEX IF NOT EXISTS skill_registry_owner_user_id_idx ON skill_registry (owner_user_id);

CREATE TABLE IF NOT EXISTS skill_artifacts (
    artifact_id UUID PRIMARY KEY,
    skill_id UUID NOT NULL REFERENCES skill_registry (skill_id),
    content_digest TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    file_count INT NOT NULL DEFAULT 0,
    total_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS skill_artifacts_skill_id_idx ON skill_artifacts (skill_id);

CREATE TABLE IF NOT EXISTS skill_imports (
    import_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    target_agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    source_uri TEXT NOT NULL,
    source_ref TEXT NULL,
    skill_path TEXT NULL,
    status TEXT NOT NULL,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    scan_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_digest TEXT NULL,
    imported_skill_id UUID NULL REFERENCES skill_registry (skill_id),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ NULL,
    confirmed_by UUID NULL REFERENCES app_users (user_id),
    failure_reason TEXT NOT NULL DEFAULT '',
    quarantine_path TEXT NULL,
    expires_at TIMESTAMPTZ NULL,
    CONSTRAINT skill_imports_status_chk CHECK (status IN ('discovered', 'downloading', 'scanning', 'awaiting_confirmation', 'approved', 'rejected', 'imported', 'failed', 'expired'))
);
CREATE INDEX IF NOT EXISTS skill_imports_user_id_idx ON skill_imports (user_id);
CREATE INDEX IF NOT EXISTS skill_imports_target_agent_idx ON skill_imports (target_agent_instance_id);
CREATE INDEX IF NOT EXISTS skill_imports_status_idx ON skill_imports (status);
-- Idempotent upgrade for imports created before lifecycle expiry was added.
ALTER TABLE skill_imports ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;

CREATE TABLE IF NOT EXISTS agent_config_versions (
    config_version_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    version_no INT NOT NULL,
    status TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    welcome_message TEXT NOT NULL DEFAULT '',
    example_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled_tool_codes JSONB NOT NULL DEFAULT '["get_current_datetime"]'::jsonb,
    workflow_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    knowledge_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_config_versions_status_chk CHECK (status IN ('draft', 'published', 'archived')),
    CONSTRAINT agent_config_versions_instance_version_uidx UNIQUE (agent_instance_id, version_no)
);
CREATE INDEX IF NOT EXISTS agent_config_versions_user_instance_idx ON agent_config_versions (user_id, agent_instance_id);
CREATE INDEX IF NOT EXISTS agent_config_versions_status_idx ON agent_config_versions (agent_instance_id, status);
-- Idempotent upgrade for databases created before knowledge selection was added.
ALTER TABLE agent_config_versions ADD COLUMN IF NOT EXISTS knowledge_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
-- Threads must keep the published/draft configuration selected at creation time.
-- NULL remains valid for legacy rows and uses the compatibility fallback in the runtime.
ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS config_version_id UUID NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'app_threads'::regclass
          AND conname = 'app_threads_config_version_fk'
    ) THEN
        ALTER TABLE app_threads
            ADD CONSTRAINT app_threads_config_version_fk
            FOREIGN KEY (config_version_id) REFERENCES agent_config_versions (config_version_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS app_threads_config_version_id_idx ON app_threads (config_version_id);
ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS thread_kind TEXT NOT NULL DEFAULT 'official';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'app_threads'::regclass
          AND conname = 'app_threads_thread_kind_chk'
    ) THEN
        ALTER TABLE app_threads
            ADD CONSTRAINT app_threads_thread_kind_chk
            CHECK (thread_kind IN ('debug', 'official'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent_config_skills (
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    skill_id UUID NOT NULL REFERENCES skill_registry (skill_id),
    priority INT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (config_version_id, skill_id)
);
CREATE INDEX IF NOT EXISTS agent_config_skills_instance_idx ON agent_config_skills (user_id, agent_instance_id);

CREATE TABLE IF NOT EXISTS agent_config_tools (
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    tool_code TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (config_version_id, tool_code)
);
CREATE INDEX IF NOT EXISTS agent_config_tools_instance_idx
    ON agent_config_tools (user_id, agent_instance_id);

CREATE TABLE IF NOT EXISTS agent_config_knowledge_documents (
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    document_id UUID NOT NULL REFERENCES agent_knowledge_documents (document_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (config_version_id, document_id)
);
CREATE INDEX IF NOT EXISTS agent_config_knowledge_documents_instance_idx
    ON agent_config_knowledge_documents (user_id, agent_instance_id);

CREATE TABLE IF NOT EXISTS agent_skills (
    skill_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    approval_mode TEXT NOT NULL DEFAULT 'once',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_skills_risk_chk CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT agent_skills_approval_chk CHECK (approval_mode IN ('auto', 'once', 'session', 'always')),
    CONSTRAINT agent_skills_status_chk CHECK (status IN ('active', 'archived'))
);
CREATE INDEX IF NOT EXISTS agent_skills_owner_idx ON agent_skills (user_id, agent_instance_id);

CREATE TABLE IF NOT EXISTS thread_skill_approvals (
    approval_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    thread_id TEXT NOT NULL,
    skill_id UUID NOT NULL REFERENCES skill_registry (skill_id),
    skill_version INT NOT NULL,
    approval_scope TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NULL,
    decided_by UUID NULL REFERENCES app_users (user_id),
    decision_reason TEXT NOT NULL DEFAULT '',
    CONSTRAINT thread_skill_approvals_scope_chk CHECK (approval_scope IN ('once', 'session', 'always')),
    CONSTRAINT thread_skill_approvals_status_chk CHECK (status IN ('pending', 'approved', 'denied', 'expired', 'revoked'))
);
CREATE INDEX IF NOT EXISTS thread_skill_approvals_scope_idx ON thread_skill_approvals (user_id, agent_instance_id, thread_id);
CREATE INDEX IF NOT EXISTS thread_skill_approvals_status_idx ON thread_skill_approvals (config_version_id, status);

CREATE TABLE IF NOT EXISTS thread_action_approvals (
    approval_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    thread_id TEXT NOT NULL,
    approval_kind TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    approval_scope TEXT NOT NULL DEFAULT 'once',
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMPTZ NULL,
    decided_by UUID NULL REFERENCES app_users (user_id),
    reason TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ NULL,
    consumed_at TIMESTAMPTZ NULL,
    CONSTRAINT thread_action_approvals_kind_chk CHECK (approval_kind IN ('import', 'skill', 'script', 'tool')),
    CONSTRAINT thread_action_approvals_scope_chk CHECK (approval_scope IN ('once', 'session', 'always')),
    CONSTRAINT thread_action_approvals_status_chk CHECK (status IN ('pending', 'approved', 'denied', 'expired', 'revoked')),
    UNIQUE (user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code, approval_scope)
);
-- Idempotent upgrades for approval scope/expiry/one-shot consumption.
ALTER TABLE thread_action_approvals ADD COLUMN IF NOT EXISTS approval_scope TEXT NOT NULL DEFAULT 'once';
ALTER TABLE thread_action_approvals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;
ALTER TABLE thread_action_approvals ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ NULL;
-- Upgrade the original uniqueness key so once/session/always grants are independent.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'thread_action_approvals'::regclass
          AND conname = 'thread_action_approvals_user_id_agent_instance_id_config_version_id_thread_id_approval_kind_resource_code_key'
    ) THEN
        ALTER TABLE thread_action_approvals
            DROP CONSTRAINT thread_action_approvals_user_id_agent_instance_id_config_version_id_thread_id_approval_kind_resource_code_key;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'thread_action_approvals'::regclass
          AND conname = 'thread_action_approvals_scope_unique'
    ) THEN
        ALTER TABLE thread_action_approvals
            ADD CONSTRAINT thread_action_approvals_scope_unique
            UNIQUE (user_id, agent_instance_id, config_version_id, thread_id, approval_kind, resource_code, approval_scope);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS thread_action_approvals_scope_idx ON thread_action_approvals (user_id, agent_instance_id, config_version_id, thread_id);
CREATE INDEX IF NOT EXISTS thread_action_approvals_kind_idx ON thread_action_approvals (approval_kind, status);
CREATE INDEX IF NOT EXISTS thread_action_approvals_scope_status_idx
    ON thread_action_approvals (user_id, agent_instance_id, config_version_id, thread_id, approval_scope, status);

CREATE TABLE IF NOT EXISTS tool_execution_records (
    execution_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    thread_id TEXT NOT NULL,
    tool_code TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    input_digest TEXT NULL,
    output_digest TEXT NULL,
    external_request_id TEXT NULL,
    error_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS tool_execution_records_scope_idx
    ON tool_execution_records (user_id, agent_instance_id, config_version_id, thread_id);
CREATE INDEX IF NOT EXISTS tool_execution_records_status_idx
    ON tool_execution_records (config_version_id, execution_status);
CREATE INDEX IF NOT EXISTS tool_execution_records_created_idx
    ON tool_execution_records (created_at);

CREATE TABLE IF NOT EXISTS skill_script_execution_records (
    execution_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users (user_id),
    agent_instance_id UUID NOT NULL REFERENCES agent_instances (agent_instance_id),
    config_version_id UUID NOT NULL REFERENCES agent_config_versions (config_version_id),
    thread_id TEXT NOT NULL,
    skill_id UUID NOT NULL REFERENCES skill_registry (skill_id),
    artifact_id UUID NULL REFERENCES skill_artifacts (artifact_id),
    script_path TEXT NOT NULL,
    interpreter TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    network_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    input_digest TEXT NULL,
    output_digest TEXT NULL,
    exit_code INT NULL,
    error_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS skill_script_execution_records_scope_idx ON skill_script_execution_records (user_id, agent_instance_id, thread_id);
CREATE INDEX IF NOT EXISTS skill_script_execution_records_created_idx ON skill_script_execution_records (created_at);
