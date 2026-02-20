WITH customer_seed AS (
    SELECT
        i,
        format('dep-%s', lpad(i::text, 4, '0')) AS deployment_id,
        format('Demo Account %s', i) AS account_name,
        CASE i % 4
            WHEN 0 THEN 'Onboarding'
            WHEN 1 THEN 'Active'
            WHEN 2 THEN 'Renewal'
            ELSE 'Expansion'
        END AS customer_stage,
        format('owner%02s@example.com', ((i - 1) % 9) + 1) AS account_owner,
        (50000 + (i * 4200))::NUMERIC(12,2) AS annual_recurring_revenue,
        format('tam%02s@example.com', ((i - 1) % 8) + 1) AS technical_account_manager,
        (CURRENT_DATE - ((i * 3) % 120))::DATE AS last_engagement_date,
        (i % 2 = 0) AS sast,
        (i % 3 = 0) AS ssc,
        (i % 4 = 0) AS secrets,
        ROUND((((i * 1.37) % 125) + 2)::NUMERIC, 2) AS active_contributors_count,
        CASE i % 3
            WHEN 0 THEN 'Green'
            WHEN 1 THEN 'Yellow'
            ELSE 'Red'
        END AS health_color,
        (CURRENT_DATE + ((i * 13) % 365))::DATE AS latest_contract_end_date,
        (i % 6) AS open_critical_feature_request,
        (i * 2) % 90 AS days_since_last_contact,
        (CURRENT_DATE + ((i * 17) % 420))::DATE AS license_expiration_date,
        (20 + i * 4) AS total_contributors,
        (5 + (i % 45)) AS contributors_last_30_days,
        CURRENT_TIMESTAMP AS insert_time
    FROM generate_series(1, 67) AS s(i)
)
INSERT INTO "Customer_Success" (
    deployment_id,
    account_name,
    customer_stage,
    account_owner,
    annual_recurring_revenue,
    technical_account_manager,
    last_engagement_date,
    sast,
    ssc,
    secrets,
    active_contributors_count,
    health_color,
    latest_contract_end_date,
    open_critical_feature_request,
    days_since_last_contact,
    license_expiration_date,
    total_contributors,
    contributors_last_30_days,
    insert_time
)
SELECT
    deployment_id,
    account_name,
    customer_stage,
    account_owner,
    annual_recurring_revenue,
    technical_account_manager,
    last_engagement_date,
    sast,
    ssc,
    secrets,
    active_contributors_count,
    health_color,
    latest_contract_end_date,
    open_critical_feature_request,
    days_since_last_contact,
    license_expiration_date,
    total_contributors,
    contributors_last_30_days,
    insert_time
FROM customer_seed
ON CONFLICT (deployment_id) DO UPDATE SET
    account_name = EXCLUDED.account_name,
    customer_stage = EXCLUDED.customer_stage,
    account_owner = EXCLUDED.account_owner,
    annual_recurring_revenue = EXCLUDED.annual_recurring_revenue,
    technical_account_manager = EXCLUDED.technical_account_manager,
    last_engagement_date = EXCLUDED.last_engagement_date,
    sast = EXCLUDED.sast,
    ssc = EXCLUDED.ssc,
    secrets = EXCLUDED.secrets,
    active_contributors_count = EXCLUDED.active_contributors_count,
    health_color = EXCLUDED.health_color,
    latest_contract_end_date = EXCLUDED.latest_contract_end_date,
    open_critical_feature_request = EXCLUDED.open_critical_feature_request,
    days_since_last_contact = EXCLUDED.days_since_last_contact,
    license_expiration_date = EXCLUDED.license_expiration_date,
    total_contributors = EXCLUDED.total_contributors,
    contributors_last_30_days = EXCLUDED.contributors_last_30_days,
    insert_time = EXCLUDED.insert_time;

WITH health_seed AS (
    SELECT
        format('Demo Account %s', i) AS account_name,
        ROUND(
            (
                CASE i % 3
                    WHEN 0 THEN 100
                    WHEN 1 THEN 50
                    ELSE 0
                END
                + CASE i % 6
                    WHEN 0 THEN 100
                    WHEN 1 THEN 75
                    WHEN 2 THEN 50
                    WHEN 3 THEN 25
                    ELSE 0
                END
                + LEAST(100, ROUND((((i * 1.37) % 125) + 2)::NUMERIC, 2))
                + GREATEST(0, 100 - ((i * 2) % 90))
            ) / 4.0
        , 2)::NUMERIC(5,2) AS health_score,
        CURRENT_TIMESTAMP AS insert_time
    FROM generate_series(1, 67) AS s(i)
)
INSERT INTO "Customer_success_health_score" (
    account_name,
    health_score,
    insert_time
)
SELECT account_name, health_score, insert_time
FROM health_seed;

WITH fr_seed AS (
    SELECT
        i,
        format('FR-%s', lpad(i::text, 4, '0')) AS case_number,
        format('owner%02s@example.com', ((i - 1) % 9) + 1) AS case_owner,
        format('Demo Account %s', ((i - 1) % 67) + 1) AS account_name,
        format('Demo feature request %s', i) AS subject,
        CASE WHEN i % 4 = 0 THEN 'Closed' ELSE 'Open' END AS status,
        CASE i % 4
            WHEN 0 THEN 'Renewal'
            WHEN 1 THEN 'Expansion'
            WHEN 2 THEN 'Upsell'
            ELSE 'None'
        END AS opportunity,
        format('Requested capability %s', i) AS feature_request,
        CASE
            WHEN i % 5 = 0 THEN NULL
            ELSE format('https://linear.app/demo/issue/FR-%s', i)
        END AS linear_url_fr,
        (CURRENT_DATE - (i % 365))::DATE AS date_time_opened,
        CASE i % 4
            WHEN 0 THEN 'P0'
            WHEN 1 THEN 'P1'
            WHEN 2 THEN 'P2'
            ELSE 'P3'
        END::feature_request_priority AS priority,
        (i % 4 <> 0) AS open,
        (i % 4 = 0) AS closed,
        format('tam%02s@example.com', ((i - 1) % 8) + 1) AS technical_account_manager,
        CASE i % 4
            WHEN 0 THEN 'Done'
            WHEN 1 THEN 'Planned'
            WHEN 2 THEN 'In progress'
            ELSE 'Backlog'
        END AS feature_request_status,
        CURRENT_TIMESTAMP AS insert_time
    FROM generate_series(1, 225) AS s(i)
)
INSERT INTO feature_request (
    case_number,
    case_owner,
    account_name,
    subject,
    status,
    opportunity,
    feature_request,
    linear_url_fr,
    date_time_opened,
    priority,
    open,
    closed,
    technical_account_manager,
    feature_request_status,
    insert_time
)
SELECT
    case_number,
    case_owner,
    account_name,
    subject,
    status,
    opportunity,
    feature_request,
    linear_url_fr,
    date_time_opened,
    priority,
    open,
    closed,
    technical_account_manager,
    feature_request_status,
    insert_time
FROM fr_seed
ON CONFLICT (case_number) DO UPDATE SET
    case_owner = EXCLUDED.case_owner,
    account_name = EXCLUDED.account_name,
    subject = EXCLUDED.subject,
    status = EXCLUDED.status,
    opportunity = EXCLUDED.opportunity,
    feature_request = EXCLUDED.feature_request,
    linear_url_fr = EXCLUDED.linear_url_fr,
    date_time_opened = EXCLUDED.date_time_opened,
    priority = EXCLUDED.priority,
    open = EXCLUDED.open,
    closed = EXCLUDED.closed,
    technical_account_manager = EXCLUDED.technical_account_manager,
    feature_request_status = EXCLUDED.feature_request_status,
    insert_time = EXCLUDED.insert_time;
