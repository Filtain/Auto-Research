CREATE TABLE research_projects (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    topic TEXT,
    status TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE research_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    task_name TEXT,
    agent_name TEXT,
    status TEXT,
    input_json JSONB,
    output_json JSONB,
    depends_on JSONB,
    retry_count INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE research_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    artifact_name TEXT,
    artifact_type TEXT,
    file_path TEXT,
    source_tasks JSONB,
    verified BOOLEAN,
    created_at TIMESTAMP
);

CREATE TABLE evidence_items (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    source_title TEXT,
    source_url TEXT,
    paper_id TEXT,
    page_number INTEGER,
    section_name TEXT,
    quote TEXT,
    claim TEXT,
    confidence FLOAT
);
