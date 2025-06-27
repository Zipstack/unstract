from migrating.v2.query import MigrationQuery


class UnstractMigration(MigrationQuery):
    """This class contains methods to generate SQL queries for various cloud
    table migration operations."""

    def get_public_schema_migrations(self) -> list[dict[str, str]]:
        """Returns a list of dictionaries containing the schema migration
        details.

        Args:
            v2_schema (str): The name of the schema in the version 2 database.

        Returns:
            list: A list of dictionaries containing the schema migration
            details.
        """
        core_public_schema_migrations = super().get_public_schema_migrations()
        migrations = [
            {
                "name": "migration_015_subscription",
                "src_query": """
                    SELECT id, start_date, end_date, plan_name, is_paid,
                    is_active, organization_id
                    FROM subscription_subscription;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".subscription (
                        id, start_date, end_date, plan_name, is_paid,
                        is_active, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "subscription",
            },
            {
                "name": "migration_017_share_manager",
                "src_query": """
                    SELECT share_id, tool_id, share_type, organization_id
                    FROM share_manager_sharemanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".share_manager (
                        share_id, tool_id, share_type, organization_id
                    ) VALUES (%s, %s, %s, %s);
                """,
                "dest_table": "share_manager",
            },
            {
                "name": "migration_19_sps_project",
                "src_query": """
                    SELECT tool_id, tool_name, created_at, modified_at
                    FROM sps_project;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".sps_project (
                        tool_id, tool_name, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s);
                """,
                "dest_table": "sps_project",
            },
            {
                "name": "migration_018_sps_document",
                "src_query": """
                    SELECT document_id, document_name, tool_id, index_status,
                        created_at, modified_at
                    FROM sps_document;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".sps_document (
                        document_id, document_name, tool_id, index_status,
                        created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "sps_document",
            },
            {
                "name": "migration_20_sps_prompt",
                "src_query": """
                    SELECT prompt_id, tool_id_id, prompt_key, prompt,
                        sequence_number, created_at, modified_at
                    FROM sps_prompt;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".sps_prompt (
                        prompt_id, tool_id_id, prompt_key, prompt,
                        sequence_number, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "sps_prompt",
            },
            {
                "name": "migration_21_sps_prompt_output",
                "src_query": """
                    SELECT prompt_output_id, output, prompt_id_id,
                        document_manager_id, tool_id_id, created_at, modified_at
                    FROM sps_prompt_output_spspromptoutput;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".sps_prompt_output (
                        prompt_output_id, output, prompt_id_id,
                        document_manager_id, tool_id_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "sps_prompt_output",
            },
        ]
        return core_public_schema_migrations + migrations

    def get_organization_migrations(
        self, schema: str, organization_id: str
    ) -> list[dict[str, str]]:
        """
        Returns a list of dictionaries containing the organization
        migration details.
        Args:
            schema_name (str): The name of the schema for the organization.
            organization_id (str): The ID of the organization.

        Returns:
            list: A list of dictionaries containing the organization
                migration details.
        """
        core_organization_migrations = super().get_organization_migrations(
            schema, organization_id
        )
        migrations = [
            {
                "name": f"migration_{schema}_app_deployment",
                "src_query": f"""
                    SELECT id, app_display_name, app_name, description,
                        workflow_id, is_active, created_by_id,
                        modified_by_id, created_at, modified_at
                    FROM "{schema}".app_deployment_appdeployment;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".app_deployment (
                        id, app_display_name, app_name, description,
                        workflow_id, is_active, created_by_id, modified_by_id,
                        created_at, modified_at, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    {organization_id});
                """,
                "dest_table": "app_deployment",
            },
            {
                "name": f"migration_{schema}_indexed_documents",
                "src_query": f"""
                    SELECT id, file_name, document_id, app_deployment_id,
                        created_at, modified_at
                    FROM "{schema}".app_deployment_indexeddocuments;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".indexed_documents (
                        id, file_name, document_id, app_deployment_id,
                        created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "indexed_documents",
            },
            {
                "name": f"migration_{schema}_appdeployment_shared_users",
                "src_query": f"""
                    SELECT id, appdeployment_id, user_id
                    FROM "{schema}".
                    app_deployment_appdeployment_shared_users;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".app_deployment_shared_users (
                        id, appdeployment_id, user_id
                    ) VALUES (%s, %s, %s);
                """,
                "dest_table": "app_deployment_shared_users",
            },
            {
                "name": f"migration_{schema}_canned_question",
                "src_query": f"""
                    SELECT id, question, is_active, app_deployment_id,
                        created_by_id, modified_by_id, created_at, modified_at
                    FROM "{schema}".canned_question_cannedquestion;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".canned_question (
                        id, question, is_active, app_deployment_id,
                        created_by_id, modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "canned_question",
            },
            {
                "name": f"migration_{schema}_chat_history",
                "src_query": f"""
                    SELECT id, label, app_deployment_id, created_by_id,
                        modified_by_id, session_id, created_at, modified_at
                    FROM "{schema}".chat_history_chathistory;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".chat_history (
                        id, label, app_deployment_id, created_by_id,
                        modified_by_id, session_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "chat_history",
            },
            {
                "name": f"migration_{schema}_chat_transcript",
                "src_query": f"""
                    SELECT id, message, role, chat_history_id, created_by_id,
                    modified_by_id, created_at, modified_at
                    FROM "{schema}".chat_transcript_chattranscript;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".chat_transcript (
                        id, message, role, chat_history_id, created_by_id,
                        modified_by_id, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                "dest_table": "chat_transcript",
            },
            {
                "name": f"migration_{schema}_prompt_clone_manager",
                "src_query": f"""
                    SELECT id, parent_tool_id, clone_tool_id, created_at,
                    modified_at
                    FROM "{schema}".clone_promptclonemanager;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".prompt_clone_manager (
                        id, parent_tool_id, clone_tool_id, created_at,
                        modified_at
                    ) VALUES (%s, %s, %s, %s, %s);
                """,
                "dest_table": "prompt_clone_manager",
            },
            {
                "name": f"migration_{schema}_table_settings",
                "src_query": f"""
                    SELECT id, tool_id, prompt_id, start_page, end_page,
                        document_type, compress_double_space, headers,
                        disable_span_search, page_delimiter,
                        use_form_feed, enforce_type, created_at, modified_at
                    FROM "{schema}".table_settings_tablesettings;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".table_settings (
                        id, tool_id, prompt_id, start_page, end_page,
                        document_type, compress_double_space, headers,
                        disable_span_search, page_delimiter,
                        use_form_feed, enforce_type, created_at, modified_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s);
                """,
                "dest_table": "table_settings",
                "type_transformations": {
                    "headers": {
                        "type": "list",
                    }
                },
            },
            {
                "name": f"migration_{schema}_review_api_key",
                "src_query": f"""
                    SELECT id, api_key, class_name, description, is_active,
                        created_by_id, modified_by_id
                    FROM "{schema}".manual_review_reviewapikey;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".review_api_key (
                        id, api_key, class_name, description, is_active,
                        created_by_id, modified_by_id, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, {organization_id});
                """,
                "dest_table": "review_api_key",
            },
            {
                "name": f"migration_{schema}_db_rules",
                "src_query": f"""
                    SELECT id, workflow_id, percentage, created_by_id,
                        modified_by_id
                    FROM "{schema}".manual_review_dbrules;
                """,
                "dest_query": f"""
                    INSERT INTO "{self.v2_schema}".db_rules (
                        id, workflow_id, percentage, created_by_id,
                        modified_by_id, organization_id
                    ) VALUES (%s, %s, %s, %s, %s, {organization_id});
                """,
                "dest_table": "db_rules",
            },
        ]
        return core_organization_migrations + migrations
