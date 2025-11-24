"""Synchronous pipeline orchestration with WebSocket progress tracking.

This service orchestrates all AutoPrompt pipelines using synchronous HTTP calls
to the prompt-service, with real-time progress updates via Django Channels WebSocket.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import models
from platform_settings_v2.platform_auth_service import PlatformAuthenticationService

from ..models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticExtractedData,
    AgenticProject,
    AgenticPromptVersion,
    AgenticSchema,
    AgenticSummary,
    AgenticVerifiedData,
)

logger = logging.getLogger(__name__)


class PipelineService:
    """Orchestrates multi-stage document processing pipelines synchronously."""

    def __init__(self, project_id: str):
        """Initialize pipeline for a project.

        Args:
            project_id: Project UUID as string
        """
        self.project_id = project_id
        self.project = AgenticProject.objects.get(id=project_id)
        self.channel_layer = get_channel_layer()
        self.prompt_service_url = f"{settings.PROMPT_HOST}:{settings.PROMPT_PORT}"

        # Get platform key for SDK authentication
        try:
            platform_key = PlatformAuthenticationService.get_active_platform_key(
                organization_id=str(self.project.organization.organization_id)
            )
            self.platform_key = str(platform_key.key)
        except Exception as e:
            logger.error(f"Failed to get platform key: {e}")
            self.platform_key = ""

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for prompt-service requests.

        Returns:
            Dict with required headers including X-Platform-Key
        """
        return {
            "Content-Type": "application/json",
            "X-Platform-Key": self.platform_key,
        }

    def send_progress(
        self,
        stage: str,
        status: str,
        progress: int,
        message: str,
        agent_name: Optional[str] = None,
    ):
        """Send progress update via WebSocket.

        Args:
            stage: Pipeline stage (schema, prompt, extraction, tuning)
            status: Status (processing, complete, error)
            progress: Percentage (0-100)
            message: Human-readable message
            agent_name: Current agent name (optional)
        """
        try:
            async_to_sync(self.channel_layer.group_send)(
                f"agentic_progress_{self.project_id}",
                {
                    "type": "progress_update",
                    "data": {
                        "stage": stage,
                        "status": status,
                        "progress": progress,
                        "message": message,
                        "agent_name": agent_name,
                    },
                },
            )
            logger.debug(
                f"Progress sent: {stage} {progress}% - {message} (agent: {agent_name})"
            )
        except Exception as e:
            logger.error(f"Failed to send progress update: {e}")

    # ============================================================================
    # PIPELINE 1: LAZY SCHEMA GENERATION (Auto-Dependencies)
    # ============================================================================

    def generate_schema_lazy(self) -> Dict[str, Any]:
        """Generate schema with automatic dependency handling.

        Phases:
        1. Raw text extraction (0-30%) - for documents missing raw_text
        2. Summarization (30-70%) - for documents missing summaries
        3. Schema generation (70-100%) - Uniformer + Finalizer

        Returns:
            dict with schema_id and processing summary

        Raises:
            ValueError: If processing fails
        """
        logger.info(f"Starting lazy schema generation for project {self.project_id}")

        try:
            # PHASE 1: Raw Text Extraction (0-30%)
            self.send_progress(
                stage="schema",
                status="processing",
                progress=0,
                message="Checking for documents needing raw text extraction...",
            )

            docs_without_text = self.project.documents.filter(
                raw_text__isnull=True
            ) | self.project.documents.filter(raw_text="")
            total_docs = self.project.documents.count()

            if total_docs == 0:
                raise ValueError("No documents uploaded. Please upload documents first.")

            if docs_without_text.exists():
                count = docs_without_text.count()
                logger.info(f"Processing raw text for {count} documents")

                self.send_progress(
                    stage="schema",
                    status="processing",
                    progress=5,
                    message=f"Extracting text from {count} documents...",
                    agent_name="LLMWhispererAgent",
                )

                for idx, doc in enumerate(docs_without_text, 1):
                    try:
                        self._process_raw_text_sync(doc)
                        progress = int(5 + (idx / count) * 25)  # 5% to 30%
                        self.send_progress(
                            stage="schema",
                            status="processing",
                            progress=progress,
                            message=f"Extracting text from document {idx}/{count}: {doc.original_filename}",
                            agent_name="LLMWhispererAgent",
                        )
                    except Exception as e:
                        logger.error(f"Failed to extract text from {doc.original_filename}: {e}")
                        # Continue with other documents instead of failing completely
                        doc.processing_error = str(e)
                        doc.save()

            self.send_progress(
                stage="schema",
                status="processing",
                progress=30,
                message="Raw text extraction complete",
            )

            # PHASE 2: Summarization (30-70%)
            self.send_progress(
                stage="schema",
                status="processing",
                progress=30,
                message="Checking for documents needing summaries...",
            )

            # Get documents with text
            docs_with_text = self.project.documents.exclude(raw_text__isnull=True).exclude(
                raw_text=""
            )

            if not docs_with_text.exists():
                raise ValueError(
                    "No documents have raw text. Please ensure documents are processed or LLMWhisperer is configured correctly."
                )

            # Find documents needing summaries
            docs_needing_summaries = []
            for doc in docs_with_text:
                if not AgenticSummary.objects.filter(document=doc).exists():
                    docs_needing_summaries.append(doc)

            if docs_needing_summaries:
                count = len(docs_needing_summaries)
                logger.info(f"Generating summaries for {count} documents")

                self.send_progress(
                    stage="schema",
                    status="processing",
                    progress=35,
                    message=f"Generating summaries for {count} documents...",
                    agent_name="SummarizerAgent",
                )

                for idx, doc in enumerate(docs_needing_summaries, 1):
                    try:
                        self._process_summary_sync(doc)
                        progress = int(35 + (idx / count) * 35)  # 35% to 70%
                        self.send_progress(
                            stage="schema",
                            status="processing",
                            progress=progress,
                            message=f"Generating summary {idx}/{count}: {doc.original_filename}",
                            agent_name="SummarizerAgent",
                        )
                    except Exception as e:
                        logger.error(f"Failed to generate summary for {doc.original_filename}: {e}")
                        # Continue with other documents
                        continue

            self.send_progress(
                stage="schema",
                status="processing",
                progress=70,
                message="Summarization complete",
            )

            # PHASE 3: Schema Generation (70-100%)
            summaries = AgenticSummary.objects.filter(project=self.project)

            if not summaries.exists():
                raise ValueError(
                    "No summaries available. Cannot generate schema without document summaries."
                )

            self.send_progress(
                stage="schema",
                status="processing",
                progress=70,
                message=f"Generating schema from {summaries.count()} document summaries...",
                agent_name="UniformerAgent",
            )

            schema = self._generate_schema_sync(summaries)

            self.send_progress(
                stage="schema",
                status="complete",
                progress=100,
                message=f"Schema generated successfully with {summaries.count()} documents",
            )

            return {
                "status": "success",
                "schema_id": str(schema.id),
                "total_documents": total_docs,
                "docs_processed": summaries.count(),
                "schema_version": schema.version,
            }

        except Exception as e:
            logger.error(f"Lazy schema generation failed: {e}", exc_info=True)
            self.send_progress(
                stage="schema", status="error", progress=0, message=str(e)
            )
            raise

    def _process_raw_text_sync(self, document: AgenticDocument):
        """Process raw text extraction synchronously.

        Args:
            document: Document to process

        Raises:
            ValueError: If extraction fails
        """
        if not self.project.llmwhisperer:
            raise ValueError(
                "LLMWhisperer connector not configured. Please configure in Project Settings."
            )

        response = requests.post(
            f"{self.prompt_service_url}/agentic/extract-text",
            json={
                "document_id": str(document.id),
                "project_id": str(self.project_id),
                "file_path": document.stored_path,
                "organization_id": str(self.project.organization.organization_id),
                "adapter_instance_id": str(self.project.llmwhisperer_id),
            },
            headers=self._get_headers(),
            timeout=300,
        )

        if response.status_code != 200:
            error_msg = f"Text extraction failed: {response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        data = response.json()
        document.raw_text = data.get("raw_text", "")
        document.pages = data.get("pages", 0)
        document.processing_error = None
        document.save()

        logger.info(f"Extracted {len(document.raw_text)} characters from {document.original_filename}")

    def _process_summary_sync(self, document: AgenticDocument):
        """Process summary generation synchronously.

        Args:
            document: Document to summarize

        Raises:
            ValueError: If summarization fails
        """
        if not self.project.agent_llm:
            raise ValueError(
                "Agent LLM connector not configured. Please configure in Project Settings."
            )

        response = requests.post(
            f"{self.prompt_service_url}/agentic/summarize",
            json={
                "document_id": str(document.id),
                "project_id": str(self.project_id),
                "document_text": document.raw_text,
                "organization_id": str(self.project.organization.organization_id),
                "adapter_instance_id": str(self.project.agent_llm_id),
            },
            headers=self._get_headers(),
            timeout=300,
        )

        if response.status_code != 200:
            error_msg = f"Summarization failed: {response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        data = response.json()

        AgenticSummary.objects.update_or_create(
            project=self.project,
            document=document,
            defaults={
                "summary_text": data.get("summary_text", ""),
                "organization": self.project.organization,
            },
        )

        logger.info(f"Generated summary for {document.original_filename}")

    def _generate_schema_sync(self, summaries) -> AgenticSchema:
        """Generate schema synchronously using Uniformer + Finalizer.

        Args:
            summaries: QuerySet of AgenticSummary objects

        Returns:
            AgenticSchema instance

        Raises:
            ValueError: If schema generation fails
        """
        if not self.project.agent_llm:
            raise ValueError(
                "Agent LLM connector not configured. Please configure in Project Settings."
            )

        # Prepare summaries data
        summaries_data = []
        for summary in summaries:
            summaries_data.append(
                {
                    "document_id": str(summary.document.id),
                    "summary_text": summary.summary_text,
                }
            )

        # Step 1: Uniformize (merge field candidates)
        self.send_progress(
            stage="schema",
            status="processing",
            progress=75,
            message="Merging field candidates from all summaries...",
            agent_name="UniformerAgent",
        )

        uniform_response = requests.post(
            f"{self.prompt_service_url}/agentic/uniformize",
            json={
                "project_id": str(self.project_id),
                "summaries": summaries_data,
                "organization_id": str(self.project.organization.organization_id),
                "adapter_instance_id": str(self.project.agent_llm_id),
            },
            headers=self._get_headers(),
            timeout=600,
        )

        if uniform_response.status_code != 200:
            error_msg = f"Schema uniformization failed: {uniform_response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        uniform_schema = uniform_response.json().get("uniform_schema", {})

        # Step 2: Finalize (generate JSON Schema)
        self.send_progress(
            stage="schema",
            status="processing",
            progress=90,
            message="Generating JSON Schema...",
            agent_name="FinalizerAgent",
        )

        final_response = requests.post(
            f"{self.prompt_service_url}/agentic/finalize",
            json={
                "project_id": str(self.project_id),
                "uniform_schema": uniform_schema,
                "organization_id": str(self.project.organization.organization_id),
                "adapter_instance_id": str(self.project.agent_llm_id),
            },
            headers=self._get_headers(),
            timeout=600,
        )

        if final_response.status_code != 200:
            error_msg = f"Schema finalization failed: {final_response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        json_schema = final_response.json().get("json_schema", {})

        # Deactivate old schemas
        AgenticSchema.objects.filter(project=self.project, is_active=True).update(
            is_active=False
        )

        # Get next version number
        max_version = (
            AgenticSchema.objects.filter(project=self.project)
            .aggregate(max_version=models.Max("version"))
            .get("max_version")
            or 0
        )

        # Create new schema
        schema = AgenticSchema.objects.create(
            project=self.project,
            json_schema=json.dumps(json_schema) if isinstance(json_schema, dict) else json_schema,
            version=max_version + 1,
            is_active=True,
            created_by_agent="finalizer",
            organization=self.project.organization,
        )

        logger.info(f"Created schema version {schema.version} for project {self.project_id}")
        return schema

    # ============================================================================
    # PIPELINE 2: PROMPT GENERATION (3-Agent Pipeline)
    # ============================================================================

    def generate_prompt(self) -> AgenticPromptVersion:
        """Generate initial extraction prompt using 3-agent pipeline.

        Agents:
        1. PatternMinerAgent (25-55%) - Mine extraction hints
        2. PromptArchitectAgent (55-80%) - Draft 7-section prompt
        3. CriticDryRunnerAgent (80-95%) - Test and refine

        Returns:
            AgenticPromptVersion (newly created)

        Raises:
            ValueError: If prompt generation fails
        """
        logger.info(f"Starting prompt generation for project {self.project_id}")

        try:
            # Get schema
            schema = AgenticSchema.objects.filter(
                project=self.project, is_active=True
            ).first()
            if not schema:
                raise ValueError(
                    "No schema found. Please generate schema first by clicking 'Generate Schema' button."
                )

            # Get summaries
            summaries = AgenticSummary.objects.filter(project=self.project)
            if not summaries.exists():
                raise ValueError(
                    "No summaries found. Please generate schema first which will create summaries."
                )

            # Get 1-3 shortest documents for dry-run testing
            sample_docs = list(self.project.documents.order_by("pages")[:3])
            if not sample_docs:
                raise ValueError("No documents found for dry-run testing.")

            if not self.project.agent_llm:
                raise ValueError(
                    "Agent LLM connector not configured. Please configure in Project Settings."
                )

            self.send_progress(
                stage="prompt",
                status="processing",
                progress=0,
                message="Starting 3-agent prompt generation pipeline...",
            )

            # Call prompt-service 3-agent pipeline
            response = requests.post(
                f"{self.prompt_service_url}/agentic/generate-prompt-pipeline",
                json={
                    "project_id": str(self.project_id),
                    "schema": json.loads(schema.json_schema) if isinstance(schema.json_schema, str) else schema.json_schema,
                    "summaries": [{"summary_text": s.summary_text} for s in summaries],
                    "sample_documents": [
                        {"raw_text": d.raw_text, "filename": d.original_filename}
                        for d in sample_docs
                    ],
                    "organization_id": str(self.project.organization.organization_id),
                    "adapter_instance_id": str(self.project.agent_llm_id),
                },
                headers=self._get_headers(),
                timeout=1200,  # 20 minutes
            )

            if response.status_code != 200:
                error_msg = f"Prompt generation failed: {response.text}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            data = response.json()

            # Validate response data
            if not data:
                raise ValueError("Prompt service returned empty response")

            if not data.get("prompt_text"):
                error_detail = data.get("error", "No prompt_text in response")
                raise ValueError(f"Prompt generation failed: {error_detail}")

            # Deactivate old prompts
            AgenticPromptVersion.objects.filter(
                project=self.project, is_active=True
            ).update(is_active=False)

            # Get next version number
            from django.db.models import Max

            max_version = (
                AgenticPromptVersion.objects.filter(project=self.project)
                .aggregate(max_version=Max("version"))
                .get("max_version")
                or 0
            )

            # Create prompt version
            prompt_version = AgenticPromptVersion.objects.create(
                project=self.project,
                version=max_version + 1,
                prompt_text=data.get("prompt_text"),
                is_active=True,
                created_by_agent="prompt_architect",
                short_desc=data.get("short_desc", "Auto-generated prompt"),
                long_desc=data.get("long_desc", ""),
                organization=self.project.organization,
            )

            self.send_progress(
                stage="prompt",
                status="complete",
                progress=100,
                message=f"Prompt v{prompt_version.version} generated successfully",
            )

            logger.info(f"Created prompt version {prompt_version.version} for project {self.project_id}")
            return prompt_version

        except Exception as e:
            logger.error(f"Prompt generation failed: {e}", exc_info=True)
            self.send_progress(
                stage="prompt", status="error", progress=0, message=str(e)
            )
            raise

    # ============================================================================
    # PIPELINE 3: BATCH EXTRACTION + COMPARISON
    # ============================================================================

    def batch_extract_and_compare(self) -> Dict[str, Any]:
        """Run batch extraction on all documents with verified data,
        then auto-compare with verified data and calculate accuracy.

        Returns:
            dict with accuracy metrics

        Raises:
            ValueError: If batch extraction fails
        """
        logger.info(f"Starting batch extraction for project {self.project_id}")

        try:
            # Get active prompt
            prompt_version = self.project.prompt_versions.filter(
                is_active=True
            ).first()
            if not prompt_version:
                raise ValueError(
                    "No active prompt version found. Please generate a prompt first."
                )

            # Get documents with verified data
            verified_docs = AgenticVerifiedData.objects.filter(project=self.project)
            if not verified_docs.exists():
                raise ValueError(
                    "No verified data found. Please create verified data for at least 2 documents first."
                )

            total_docs = verified_docs.count()
            total_fields = 0
            matched_fields = 0

            self.send_progress(
                stage="extraction",
                status="processing",
                progress=0,
                message=f"Starting batch extraction for {total_docs} documents...",
            )

            for idx, verified in enumerate(verified_docs, 1):
                # Extract
                self.send_progress(
                    stage="extraction",
                    status="processing",
                    progress=int((idx / total_docs) * 50),
                    message=f"Extracting document {idx}/{total_docs}: {verified.document.original_filename}",
                    agent_name="ExtractorAgent",
                )

                try:
                    extracted = self._extract_document_sync(
                        verified.document, prompt_version
                    )
                except Exception as e:
                    logger.error(f"Failed to extract {verified.document.original_filename}: {e}")
                    continue

                # Compare
                self.send_progress(
                    stage="extraction",
                    status="processing",
                    progress=int(50 + (idx / total_docs) * 50),
                    message=f"Comparing document {idx}/{total_docs}: {verified.document.original_filename}",
                    agent_name="ComparisonAgent",
                )

                try:
                    comparison = self._compare_data_sync(extracted, verified)
                    total_fields += comparison["total_fields"]
                    matched_fields += comparison["matched_fields"]
                except Exception as e:
                    logger.error(f"Failed to compare {verified.document.original_filename}: {e}")
                    continue

            # Calculate overall accuracy
            accuracy = (matched_fields / total_fields * 100) if total_fields > 0 else 0

            # Update prompt accuracy
            prompt_version.accuracy = accuracy / 100
            prompt_version.save()

            self.send_progress(
                stage="extraction",
                status="complete",
                progress=100,
                message=f"Batch extraction complete. Accuracy: {accuracy:.2f}%",
            )

            logger.info(
                f"Batch extraction complete: {matched_fields}/{total_fields} fields matched ({accuracy:.2f}%)"
            )

            return {
                "total_documents": total_docs,
                "total_fields": total_fields,
                "matched_fields": matched_fields,
                "accuracy": accuracy,
                "prompt_version": prompt_version.version,
            }

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}", exc_info=True)
            self.send_progress(
                stage="extraction", status="error", progress=0, message=str(e)
            )
            raise

    def _extract_document_sync(
        self, document: AgenticDocument, prompt_version: AgenticPromptVersion
    ) -> AgenticExtractedData:
        """Extract data from a single document synchronously.

        Args:
            document: Document to extract from
            prompt_version: Prompt version to use

        Returns:
            AgenticExtractedData instance

        Raises:
            ValueError: If extraction fails
        """
        if not self.project.extractor_llm:
            raise ValueError(
                "Extractor LLM connector not configured. Please configure in Project Settings."
            )

        # Get schema for validation
        schema = AgenticSchema.objects.filter(
            project=self.project, is_active=True
        ).first()

        response = requests.post(
            f"{self.prompt_service_url}/agentic/extract",
            json={
                "document_id": str(document.id),
                "project_id": str(self.project_id),
                "document_text": document.raw_text,
                "prompt_text": prompt_version.prompt_text,
                "schema": json.loads(schema.json_schema) if schema and isinstance(schema.json_schema, str) else (schema.json_schema if schema else {}),
                "organization_id": str(self.project.organization.organization_id),
                "adapter_instance_id": str(self.project.extractor_llm_id),
            },
            headers=self._get_headers(),
            timeout=300,
        )

        if response.status_code != 200:
            error_msg = f"Extraction failed: {response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        data = response.json()

        # Delete old extraction for this document+prompt combination
        AgenticExtractedData.objects.filter(
            project=self.project, document=document, prompt_version=prompt_version
        ).delete()

        extracted = AgenticExtractedData.objects.create(
            project=self.project,
            document=document,
            prompt_version=prompt_version,
            data=data.get("extracted_data", {}),
            organization=self.project.organization,
        )

        logger.info(f"Extracted data from {document.original_filename}")
        return extracted

    def _compare_data_sync(
        self, extracted: AgenticExtractedData, verified: AgenticVerifiedData
    ) -> Dict[str, Any]:
        """Compare extracted vs verified data synchronously.

        Args:
            extracted: Extracted data to compare
            verified: Verified ground truth data

        Returns:
            Comparison results dict

        Raises:
            ValueError: If comparison fails
        """
        response = requests.post(
            f"{self.prompt_service_url}/agentic/compare",
            json={
                "project_id": str(self.project_id),
                "document_id": str(extracted.document.id),
                "extracted_data": extracted.data,
                "verified_data": verified.data,
                "use_llm_classification": bool(self.project.lightweight_llm_id),
                "lightweight_llm_adapter": str(self.project.lightweight_llm_id)
                if self.project.lightweight_llm_id
                else None,
                "organization_id": str(self.project.organization.organization_id),
            },
            headers=self._get_headers(),
            timeout=300,
        )

        if response.status_code != 200:
            error_msg = f"Comparison failed: {response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        comparison_data = response.json()

        # Delete old comparison results for this document
        AgenticComparisonResult.objects.filter(
            project=self.project, document=extracted.document
        ).delete()

        # Save new comparison results
        for field_result in comparison_data.get("field_results", []):
            AgenticComparisonResult.objects.create(
                project=self.project,
                document=extracted.document,
                prompt_version=extracted.prompt_version,
                field_path=field_result.get("field_path"),
                match=field_result.get("match", False),
                normalized_extracted=str(field_result.get("extracted_value", "")),
                normalized_verified=str(field_result.get("verified_value", "")),
                error_type=field_result.get("error_type"),
                organization=self.project.organization,
            )

        logger.info(
            f"Compared {extracted.document.original_filename}: "
            f"{comparison_data.get('matched_fields')}/{comparison_data.get('total_fields')} matched"
        )

        return comparison_data

    # ============================================================================
    # PIPELINE 4: PROVISIONAL VERIFIED DATA GENERATION
    # ============================================================================

    def generate_provisional_verified_data(
        self, document: AgenticDocument
    ) -> AgenticVerifiedData:
        """Generate provisional verified data for a document.

        This runs extraction and saves to verified_data table for user editing.

        Args:
            document: Document to process

        Returns:
            AgenticVerifiedData instance

        Raises:
            ValueError: If generation fails
        """
        logger.info(f"Generating provisional verified data for {document.original_filename}")

        try:
            # Get active prompt
            prompt_version = self.project.prompt_versions.filter(
                is_active=True
            ).first()
            if not prompt_version:
                raise ValueError(
                    "No active prompt version found. Please generate a prompt first."
                )

            if not self.project.extractor_llm:
                raise ValueError(
                    "Extractor LLM connector not configured. Please configure in Project Settings."
                )

            # Get schema
            schema = AgenticSchema.objects.filter(
                project=self.project, is_active=True
            ).first()

            # Run extraction
            response = requests.post(
                f"{self.prompt_service_url}/agentic/extract",
                json={
                    "document_id": str(document.id),
                    "project_id": str(self.project_id),
                    "document_text": document.raw_text,
                    "prompt_text": prompt_version.prompt_text,
                    "schema": json.loads(schema.json_schema) if schema and isinstance(schema.json_schema, str) else (schema.json_schema if schema else {}),
                    "organization_id": str(self.project.organization.organization_id),
                    "adapter_instance_id": str(self.project.extractor_llm_id),
                },
                headers=self._get_headers(),
                timeout=300,
            )

            if response.status_code != 200:
                error_msg = f"Provisional extraction failed: {response.text}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            data = response.json()

            # Save to verified_data table (user can edit later)
            verified_data, created = AgenticVerifiedData.objects.update_or_create(
                project=self.project,
                document=document,
                defaults={
                    "data": data.get("extracted_data", {}),
                    "verified_by": None,  # Not yet verified by user
                    "organization": self.project.organization,
                },
            )

            logger.info(
                f"{'Created' if created else 'Updated'} provisional verified data for {document.original_filename}"
            )
            return verified_data

        except Exception as e:
            logger.error(f"Provisional verified data generation failed: {e}", exc_info=True)
            raise
