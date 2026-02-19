DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feature_request_priority') THEN
        CREATE TYPE feature_request_priority AS ENUM (
            'P0',
            'P1',
            'P2',
            'P3',
            'LOW',
            'MEDIUM',
            'HIGH',
            'CRITICAL',
            'UNKNOWN'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS "Customer_Success" (
    deployment_id VARCHAR(100) PRIMARY KEY,
    account_name VARCHAR(255) NOT NULL,
    customer_stage VARCHAR(50),
    account_owner VARCHAR(150),
    annual_recurring_revenue NUMERIC(12,2),
    technical_account_manager VARCHAR(150),
    last_engagement_date DATE,
    sast BOOLEAN DEFAULT FALSE,
    ssc BOOLEAN DEFAULT FALSE,
    secrets BOOLEAN DEFAULT FALSE,
    active_contributors_count NUMERIC(5,2) CHECK (active_contributors_count >= 0),
    health_color VARCHAR(20) CHECK (
        health_color IS NULL OR LOWER(health_color) IN ('green', 'yellow', 'red')
    ),
    latest_contract_end_date DATE,
    open_critical_feature_request INTEGER CHECK (open_critical_feature_request >= 0),
    days_since_last_contact INTEGER CHECK (days_since_last_contact >= 0),
    license_expiration_date DATE,
    total_contributors INTEGER CHECK (total_contributors >= 0),
    contributors_last_30_days INTEGER CHECK (contributors_last_30_days >= 0),
    insert_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "Customer_success_health_score" (
    account_name VARCHAR(255) NOT NULL,
    health_score NUMERIC(5,2) NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    insert_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feature_request (
    case_number VARCHAR PRIMARY KEY,
    case_owner VARCHAR,
    account_name VARCHAR,
    subject TEXT,
    status VARCHAR,
    opportunity VARCHAR,
    feature_request VARCHAR,
    linear_url_fr TEXT,
    date_time_opened DATE,
    priority feature_request_priority,
    open BOOLEAN,
    closed BOOLEAN,
    technical_account_manager VARCHAR,
    feature_request_status VARCHAR,
    insert_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
