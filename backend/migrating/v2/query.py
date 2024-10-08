class MigrationQuery:
    """This class contains methods to generate SQL queries for various
    migration operations."""

    def __init__(self, v2_schema) -> None:
        self.v2_schema = v2_schema

    def get_public_schema_migrations(self) -> list[dict[str, str]]:
        """Returns a list of dictionaries containing the schema migration
        details.

        Args:
            v2_schema (str): The name of the schema in the version 2 database.

        Returns:
            list: A list of dictionaries containing the schema migration details.
        """
        migrations = [
            {
                "name": "001_organization",
                "src_query": """
                    SELECT id, name, display_name, organization_id, modified_at,
                    created_at, allowed_token_limit FROM account_organization;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".organization (id, name,
                    display_name, organization_id, modified_at, created_at,
                    allowed_token_limit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "organization",
            },
            {
                "name": "migration_002_user",
                "src_query": """
                    SELECT id, password, last_login, is_superuser, username,
                        first_name, last_name, email, is_staff, is_active,
                        date_joined, user_id, project_storage_created, created_by_id,
                        modified_by_id, modified_at, created_at
                    FROM account_user;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".user (
                        id, password, last_login, is_superuser, username, first_name,
                        last_name, email, is_staff, is_active, date_joined, user_id,
                        project_storage_created, created_by_id, modified_by_id,
                        modified_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s);
                """,
                "dest_table": "user",
            },
            {
                "name": "migration_003_platformkey",
                "src_query": """
                    SELECT id, key, key_name, is_active, organization_id,
                    created_by_id, modified_by_id
                    FROM account_platformkey;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".platform_key (
                        id, key, key_name, is_active, organization_id,
                        created_by_id, modified_by_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "platform_key",
            },
            {
                "name": "migration_004_periodictask",
                "src_query": """
                    SELECT id, name, task, args, kwargs, queue,
                           exchange, routing_key, expires, enabled, last_run_at,
                           total_run_count, date_changed,
                           description, crontab_id, interval_id, solar_id,
                           one_off, start_time, priority, headers,
                           clocked_id, expire_seconds
                    FROM django_celery_beat_periodictask;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".django_celery_beat_periodictask (
                        id, name, task, args, kwargs, queue, exchange, routing_key,
                        expires, enabled, last_run_at,
                        total_run_count, date_changed, description, crontab_id,
                        interval_id, solar_id, one_off,
                        start_time, priority, headers, clocked_id, expire_seconds
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "clear_table": True,
                "dest_table": "django_celery_beat_periodictask",
            },
            {
                "name": "migration_005_periodictasks",
                "src_query": """
                    SELECT ident, last_update FROM django_celery_beat_periodictasks;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".django_celery_beat_periodictasks
                    (ident, last_update)
                    VALUES (%s, %s);
                """,
                "clear_table": True,
                "dest_table": "django_celery_beat_periodictasks",
            },
            {
                "name": "migration_006_crontabschedule",
                "src_query": """
                    SELECT id, minute, hour, day_of_week, day_of_month,
                    month_of_year, timezone FROM django_celery_beat_crontabschedule;
                """,
                "dest_query": f"""
                    INSERT INTO
                        "{self.v2_schema}".django_celery_beat_crontabschedule (
                        id, minute, hour, day_of_week, day_of_month, month_of_year,
                        timezone
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "clear_table": True,
                "dest_table": "django_celery_beat_crontabschedule",
            },
            {
                "name": "migration_007_intervalschedule",
                "src_query": """
                    SELECT id, every, period FROM django_celery_beat_intervalschedule;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".django_celery_beat_intervalschedule
                    (id, every, period)
                    VALUES (%s, %s, %s);
                """,
                "clear_table": True,
                "dest_table": "django_celery_beat_intervalschedule",
            },
            {
                "name": "migration_008_clockedschedule",
                "src_query": """
                    SELECT id, clocked_time FROM django_celery_beat_clockedschedule;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".django_celery_beat_clockedschedule
                    (id, clocked_time)
                    VALUES (%s, %s);
                """,
                "clear_table": True,
                "dest_table": "django_celery_beat_clockedschedule",
            },
            {
                "name": "migration_009_djangosession",
                "src_query": """
                    SELECT session_key, session_data, expire_date FROM django_session;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".django_session (
                        session_key, session_data, expire_date
                    ) VALUES (%s, %s, %s);
                """,
                "dest_table": "django_session",
            },
            {
                "name": "migration_010_socialauth_usersocialauth",
                "src_query": """
                    SELECT id, user_id, provider, uid, extra_data, created, modified
                    FROM social_auth_usersocialauth;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".social_auth_usersocialauth (
                        id, user_id, provider, uid, extra_data, created, modified
                    ) VALUES (%s, %s, %s, %s, %s);
                """,
                "dest_table": "social_auth_usersocialauth",
            },
            {
                "name": "migration_011_socialauth_nonce",
                "src_query": """
                    SELECT id, server_url, timestamp, salt FROM social_auth_nonce;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".social_auth_nonce (
                        id, server_url, timestamp, salt
                    ) VALUES (%s, %s, %s, %s);
                """,
                "dest_table": "social_auth_nonce",
            },
            {
                "name": "migration_012_socialauth_association",
                "src_query": """
                    SELECT id, server_url, handle, secret, issued, lifetime,
                    assoc_type FROM social_auth_association;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".social_auth_association (
                        id, server_url, handle, secret, issued, lifetime, assoc_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "social_auth_association",
            },
            {
                "name": "migration_013_socialauth_code",
                "src_query": """
                    SELECT id, email, code, verified, timestamp FROM social_auth_code;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".social_auth_code (
                        id, email, code, verified, timestamp
                    ) VALUES (%s, %s, %s, %s, %s);
                """,
                "dest_table": "social_auth_code",
            },
            {
                "name": "migration_014_socialauth_partial",
                "src_query": """
                    SELECT id, token, data, next_step, backend, timestamp
                    FROM social_auth_partial;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".social_auth_partial (
                        id, token, data, next_step, backend, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "social_auth_partial",
            },
            {
                "name": "migration_016_connector_auth",
                "src_query": """
                    SELECT id, user_id, provider, uid, extra_data, created, modified
                    FROM connector_auth_connectorauth;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".connector_auth (
                        id, user_id, provider, uid, extra_data, created, modified
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "connector_auth",
            },
            {
                "name": "migration_017_page_usage",
                "src_query": """
                    SELECT id, organization_id, file_name, file_type, run_id,
                        pages_processed, file_size, created_at
                    FROM page_usage;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".page_usage (
                        id, organization_id, file_name, file_type, run_id,
                        pages_processed, file_size, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "page_usage",
            },
        ]
        return migrations

    def get_organization_migrations(
        self, schema: str, organization_id: str
    ) -> list[dict[str, str]]:
        """
        Returns a list of dictionaries containing the organization migration details.
        Args:
            schema (str): The name of the schema for the organization.
            organization_id (str): The ID of the organization.

        Returns:
            list: A list of dictionaries containing the organization migration
            details.
        """
        migrations = [
            {
                "name": f"migration_{schema}_001_organization_member",
                "src_query": f"""
                    SELECT user_id, role, is_login_onboarding_msg,
                    is_prompt_studio_onboarding_msg
                    FROM "{schema}".tenant_account_organizationmember;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".organization_member (
                        user_id, role, is_login_onboarding_msg,
                        is_prompt_studio_onboarding_msg,
                        organization_id
                    ) VALUES (%s, %s, %s, %s, {organization_id});
                """,
                "dest_table": "organization_member",
            },
            {
                "name": f"migration_{schema}_002_adapter_instance",
                "src_query": f"""
                    SELECT id, adapter_name, adapter_id, adapter_metadata,
                        adapter_metadata_b, adapter_type, created_by_id,
                        modified_by_id, is_active, shared_to_org, is_friction_less,
                        is_usable, description, modified_at, created_at
                    FROM "{schema}".adapter_adapterinstance;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".adapter_instance (
                        id, adapter_name, adapter_id, adapter_metadata,
                        adapter_metadata_b, adapter_type, created_by_id,
                        modified_by_id, is_active, shared_to_org, is_friction_less,
                        is_usable, description, modified_at, created_at,
                        organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, {organization_id});
                """,
                "dest_table": "adapter_instance",
            },
            {
                "name": f"migration_{schema}_003_workflow",
                "src_query": f"""
                    SELECT id, prompt_name, description, workflow_name, prompt_text,
                           is_active, status, llm_response, workflow_owner_id,
                           deployment_type, source_settings, destination_settings,
                           created_by_id, modified_by_id, modified_at, created_at
                    FROM "{schema}".workflow_workflow;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".workflow (
                        id, prompt_name, description, workflow_name, prompt_text,
                        is_active, status, llm_response, workflow_owner_id,
                        deployment_type, source_settings, destination_settings,
                        created_by_id, modified_by_id, modified_at, created_at,
                        organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, {organization_id});
                """,
                "dest_table": "workflow",
            },
            {
                "name": f"migration_{schema}_connector_instance",
                "src_query": f"""
                    SELECT id, connector_name, workflow_id, connector_id,
                           connector_metadata_b, connector_version, connector_type,
                           connector_auth_id, connector_mode, created_by_id,
                           modified_by_id, created_at, modified_at
                    FROM "{schema}".connector_connectorinstance;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".connector_instance (
                        id, connector_name, workflow_id, connector_id,
                        connector_metadata, connector_version, connector_type,
                        connector_auth_id, connector_mode, created_by_id,
                        modified_by_id, created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    {organization_id});
                """,
                "dest_table": "connector_instance",
            },
            {
                "name": f"migration_{schema}_workflow_endpoint",
                "src_query": f"""
                    SELECT id, workflow_id, endpoint_type, connection_type,
                    configuration, connector_instance_id,
                    modified_at, created_at
                    FROM "{schema}".workflow_endpoints;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".workflow_endpoints (
                        id, workflow_id, endpoint_type, connection_type,
                        configuration, connector_instance_id,
                        modified_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "workflow_endpoints",
            },
            {
                "name": f"migration_{schema}_api_deployment",
                "src_query": f"""
                    SELECT id, display_name, description, workflow_id, is_active,
                    api_endpoint, api_name, created_by_id, modified_by_id,
                    modified_at, created_at
                    FROM "{schema}".api_apideployment;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".api_deployment (
                        id, display_name, description, workflow_id, is_active,
                        api_endpoint, api_name, created_by_id, modified_by_id,
                        modified_at, created_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    {organization_id});
                """,
                "dest_table": "api_deployment",
            },
            {
                "name": f"migration_{schema}_api_key",
                "src_query": f"""
                    SELECT id, api_key, api_id, pipeline_id, description, is_active,
                    created_by_id, modified_by_id, created_at, modified_at
                    FROM "{schema}".api_apikey;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".api_deployment_key (
                        id, api_key, api_id, pipeline_id, description, is_active,
                        created_by_id, modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "api_deployment_key",
            },
            {
                "name": f"migration_{schema}_pipeline",
                "src_query": f"""
                    SELECT id, pipeline_name, workflow_id, app_id, active, scheduled,
                        cron_string, pipeline_type, run_count,
                        last_run_time, last_run_status, app_icon, app_url,
                        access_control_bundle_id, created_by_id, modified_by_id,
                        created_at, modified_at
                    FROM "{schema}".pipeline_pipeline;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".pipeline (
                        id, pipeline_name, workflow_id, app_id, active, scheduled,
                        cron_string, pipeline_type, run_count,
                        last_run_time, last_run_status, app_icon, app_url,
                        access_control_bundle_id, created_by_id, modified_by_id,
                        created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, {organization_id});
                """,
                "dest_table": "pipeline",
            },
            {
                "name": f"migration_{schema}_usage",
                "src_query": f"""
                    SELECT id, workflow_id, execution_id, adapter_instance_id, run_id,
                        usage_type, llm_usage_reason, model_name,
                        embedding_tokens, prompt_tokens, completion_tokens,
                        total_tokens, cost_in_dollars,
                        created_at, modified_at
                    FROM "{schema}".token_usage;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".usage (
                        id, workflow_id, execution_id, adapter_instance_id, run_id,
                        usage_type, llm_usage_reason, model_name,
                        embedding_tokens, prompt_tokens, completion_tokens,
                        total_tokens, cost_in_dollars,
                        created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, {organization_id});
                """,
                "dest_table": "usage",
            },
            {
                "name": f"migration_{schema}_workflow_execution",
                "src_query": f"""
                    SELECT id, pipeline_id, task_id, workflow_id, execution_mode,
                           execution_method, execution_type, execution_log_id, status,
                           error_message, attempts, execution_time, created_at,
                           modified_at
                    FROM "{schema}".workflow_workflowexecution;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".workflow_execution (
                        id, pipeline_id, task_id, workflow_id, execution_mode,
                        execution_method, execution_type, execution_log_id, status,
                        error_message, attempts, execution_time, created_at,
                        modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "workflow_execution",
            },
            {
                "name": f"migration_{schema}_file_history",
                "src_query": f"""
                    SELECT id, cache_key, workflow_id, status, error, result,
                    meta_data, created_at, modified_at
                    FROM "{schema}".workflow_filehistory;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".file_history (
                        id, cache_key, workflow_id, status, error, result, metadata,
                        created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "file_history",
            },
            {
                "name": f"migration_{schema}_execution_log",
                "src_query": f"""
                    SELECT id, execution_id, data, event_time, created_at, modified_at
                    FROM "{schema}".workflow_executionlog;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".execution_log (
                        id, execution_id, data, event_time, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "execution_log",
            },
            {
                "name": f"migration_{schema}_user_default_adapter",
                "src_query": f"""
                    SELECT
                        user_id,
                        default_llm_adapter_id,
                        default_embedding_adapter_id,
                        default_vector_db_adapter_id,
                        default_x2text_adapter_id,
                        created_at,
                        modified_at
                    FROM "{schema}".adapter_processor_userdefaultadapter;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".default_organization_user_adapter (
                        organization_member_id,
                        default_llm_adapter_id,
                        default_embedding_adapter_id,
                        default_vector_db_adapter_id,
                        default_x2text_adapter_id,
                        created_at,
                        modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "default_organization_user_adapter",
                "new_key_transaction": {
                    "user_id": {
                        "query": f"""
                            SELECT member_id
                            FROM "{self.v2_schema}".organization_member
                            WHERE user_id = %s AND organization_id='{organization_id}';
                        """,
                        "params": ["user_id"],
                        "none_action": "DELETE",
                    }
                },
            },
            # Prompt studio models
            {
                "name": f"migration_{schema}_custom_tool",
                "src_query": f"""
                    SELECT tool_id, tool_name, description, author, icon, output,
                        log_id, summarize_context, summarize_as_source,
                        summarize_prompt, preamble, postamble,
                        prompt_grammer, monitor_llm_id, created_by_id,
                        modified_by_id, exclude_failed,
                        single_pass_extraction_mode, challenge_llm_id,
                        enable_challenge, enable_highlight, created_at, modified_at
                    FROM "{schema}".prompt_studio_core_customtool;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".custom_tool (
                        tool_id, tool_name, description, author, icon, output,
                        log_id, summarize_context, summarize_as_source,
                        summarize_prompt, preamble, postamble,
                        prompt_grammer, monitor_llm_id, created_by_id,
                        modified_by_id, exclude_failed,
                        single_pass_extraction_mode, challenge_llm_id,
                        enable_challenge,
                        enable_highlight, created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, {organization_id});
                """,
                "dest_table": "custom_tool",
            },
            {
                "name": f"migration_{schema}_custom_tool_shared_users",
                "src_query": f"""
                    SELECT customtool_id, user_id
                    FROM "{schema}".prompt_studio_core_customtool_shared_users;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".custom_tool_shared_users (
                        customtool_id, user_id
                    ) VALUES (%s, %s);
                """,
                "dest_table": "custom_tool_shared_users",
            },
            {
                "name": f"migration_{schema}_profile_manager",
                "src_query": f"""
                    SELECT profile_id, profile_name, vector_store_id,
                        embedding_model_id, llm_id,
                        x2text_id, chunk_size, chunk_overlap, reindex,
                        retrieval_strategy, similarity_top_k, section, created_by_id,
                        modified_by_id, prompt_studio_tool_id, is_default,
                        is_summarize_llm, created_at, modified_at
                    FROM "{schema}".prompt_profile_manager_profilemanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".profile_manager (
                        profile_id, profile_name, vector_store_id,
                        embedding_model_id, llm_id,
                        x2text_id, chunk_size, chunk_overlap, reindex,
                        retrieval_strategy, similarity_top_k, section,
                        created_by_id, modified_by_id,
                        prompt_studio_tool_id, is_default, is_summarize_llm,
                        created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s);
                """,
                "dest_table": "profile_manager",
            },
            {
                "name": f"migration_{schema}_document_manager",
                "src_query": f"""
                    SELECT document_id, document_name, tool_id, created_by_id,
                        modified_by_id, created_at, modified_at
                    FROM
                    "{schema}".prompt_studio_document_manager_documentmanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".document_manager (
                        document_id, document_name, tool_id, created_by_id,
                        modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "document_manager",
            },
            {
                "name": f"migration_{schema}_index_manager",
                "src_query": f"""
                    SELECT index_manager_id, document_manager_id, profile_manager_id,
                           raw_index_id, summarize_index_id, index_ids_history,
                           created_by_id, modified_by_id, created_at, modified_at
                    FROM "{schema}".prompt_studio_index_manager_indexmanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".index_manager (
                        index_manager_id, document_manager_id, profile_manager_id,
                        raw_index_id, summarize_index_id, index_ids_history,
                        created_by_id, modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "index_manager",
            },
            {
                "name": f"migration_{schema}_tool_studio_prompt",
                "src_query": f"""
                    SELECT prompt_id, prompt_key, enforce_type, prompt, tool_id_id,
                        sequence_number, prompt_type, profile_manager_id, output,
                        assert_prompt, assertion_failure_prompt, is_assert, active,
                        output_metadata, created_by_id, modified_by_id, evaluate,
                        eval_quality_faithfulness, eval_quality_correctness,
                        eval_quality_relevance, eval_security_pii,
                        eval_guidance_toxicity, eval_guidance_completeness,
                        created_at, modified_at
                    FROM "{schema}".prompt_studio_toolstudioprompt;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".tool_studio_prompt (
                        prompt_id, prompt_key, enforce_type, prompt, tool_id_id,
                        sequence_number, prompt_type, profile_manager_id, output,
                        assert_prompt, assertion_failure_prompt, is_assert, active,
                        output_metadata, created_by_id, modified_by_id, evaluate,
                        eval_quality_faithfulness, eval_quality_correctness,
                        eval_quality_relevance, eval_security_pii,
                        eval_guidance_toxicity, eval_guidance_completeness,
                        created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "tool_studio_prompt",
            },
            {
                "name": f"migration_{schema}_prompt_studio_output_manager",
                "src_query": f"""
                    SELECT prompt_output_id, output, context, eval_metrics,
                           is_single_pass_extract,
                           prompt_id_id, document_manager_id, profile_manager_id,
                           tool_id_id, run_id,
                           created_by_id, modified_by_id, created_at, modified_at
                    FROM
                    "{schema}".prompt_studio_output_manager_promptstudiooutputmanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".prompt_studio_output_manager (
                        prompt_output_id, output, context, eval_metrics,
                        is_single_pass_extract,
                        prompt_id_id, document_manager_id, profile_manager_id,
                        tool_id_id, run_id,
                        created_by_id, modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s);
                """,
                "dest_table": "prompt_studio_output_manager",
            },
            {
                "name": f"migration_{schema}_prompt_studio_registry",
                "src_query": f"""
                    SELECT prompt_registry_id, name, description, tool_property,
                           tool_spec,
                           tool_metadata, icon, url, custom_tool_id, created_by_id,
                           modified_by_id,
                           shared_to_org, created_at, modified_at
                    FROM "{schema}".prompt_studio_registry_promptstudioregistry;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".prompt_studio_registry (
                        prompt_registry_id, name, description, tool_property,
                        tool_spec,
                        tool_metadata, icon, url, custom_tool_id, created_by_id,
                        modified_by_id,
                        shared_to_org, created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, {organization_id});
                """,
                "dest_table": "prompt_studio_registry",
            },
            {
                "name": f"migration_{schema}_prompt_studio_registry_shared_users",
                "src_query": f"""
                    SELECT promptstudioregistry_id, user_id
                    FROM
                    "{schema}".prompt_studio_registry_promptstudioregistry_shared_users;
                """,
                "dest_query": f"""
                    INSERT INTO
                        "{self.v2_schema}".prompt_studio_registry_shared_users (
                        promptstudioregistry_id, user_id
                    ) VALUES (%s, %s);
                """,
                "dest_table": "prompt_studio_registry_shared_users",
            },
            {
                "name": f"migration_{schema}_notification",
                "src_query": f"""
                    SELECT id, name, url, authorization_key, authorization_header,
                        authorization_type, max_retries, platform, notification_type,
                        is_active, pipeline_id, api_id, created_at, modified_at
                    FROM "{schema}".notification_notification;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".notification (
                        id, name, url, authorization_key, authorization_header,
                        authorization_type, max_retries, platform, notification_type,
                        is_active, pipeline_id, api_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "notification",
            },
        ]
        return migrations
