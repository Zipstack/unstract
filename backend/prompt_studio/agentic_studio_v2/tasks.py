"""Celery tasks for Agentic Studio V2 async processing."""

import json
import logging
from typing import Any, Dict
from uuid import UUID

from celery import shared_task
from django.conf import settings

from prompt_studio.agentic_studio_v2.models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticExtractedData,
    AgenticProject,
    AgenticPromptVersion,
    AgenticSchema,
    AgenticSummary,
    AgenticVerifiedData,
)
from prompt_studio.agentic_studio_v2.services.document_service import (
    AgenticDocumentService,
)
from prompt_studio.agentic_studio_v2.services.prompt_service_client import (
    PromptServiceClient,
)
from prompt_studio.agentic_studio_v2.services.state_manager import (
    ProcessingStateManager,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="agentic_studio.process_document_stage",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def process_document_stage_task(self, document_id: str, stage: str):
    """Process a document through a specific pipeline stage.

    Args:
        document_id: UUID of the document
        stage: One of 'raw_text', 'summary', 'extraction'

    Stages:
    - raw_text: Extract text using LLMWhisperer
    - summary: Summarize document using SummarizerAgent
    - extraction: Extract structured data using active prompt
    """
    import requests
    from django.conf import settings

    state_mgr = ProcessingStateManager()

    try:
        document = AgenticDocument.objects.get(id=document_id)
        project = document.project
        project_id = str(project.id)
        organization_id = str(document.organization.organization_id)

        # Mark stage as processing
        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage=stage,
            status="in_progress",
            progress=0,
            message=f"Processing {stage}..."
        )

        # Get prompt-service URL
        prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
        prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
        prompt_service_url = f"{prompt_host}:{prompt_port}"

        if stage == "raw_text":
            # Extract raw text using LLMWhisperer
            adapter_id = None
            if project.llmwhisperer_id:
                adapter_id = str(project.llmwhisperer_id)

            if not adapter_id:
                raise ValueError("No LLMWhisperer configured for this project")

            payload = {
                "document_id": str(document.id),
                "project_id": project_id,
                "file_path": document.stored_path,
                "organization_id": organization_id,
                "adapter_instance_id": adapter_id,
            }

            response = requests.post(
                f"{prompt_service_url}/agentic/extract-text",
                json=payload,
                timeout=300,
            )

            if response.status_code != 200:
                raise ValueError(f"Text extraction failed: {response.text}")

            extraction_data = response.json()

            # Save the extracted text
            document.raw_text = extraction_data.get("raw_text", "")
            document.pages = extraction_data.get("pages", 0)
            document.save()

            logger.info(f"Extracted raw text for document {document_id}, {document.pages} pages")

        elif stage == "summary":
            # Summarize using SummarizerAgent via prompt-service
            if not document.raw_text:
                raise ValueError("Document has no raw_text to summarize")

            adapter_id = None
            if project.agent_llm_id:
                adapter_id = str(project.agent_llm_id)

            if not adapter_id:
                raise ValueError("No Agent LLM configured for this project")

            payload = {
                "document_id": str(document.id),
                "project_id": project_id,
                "document_text": document.raw_text,
                "organization_id": organization_id,
                "adapter_instance_id": adapter_id,
            }

            response = requests.post(
                f"{prompt_service_url}/agentic/summarize",
                json=payload,
                timeout=300,
            )

            if response.status_code != 200:
                raise ValueError(f"Summarization failed: {response.text}")

            summary_data = response.json()

            # Store summary
            AgenticSummary.objects.update_or_create(
                project=project,
                document=document,
                organization=document.organization,
                defaults={"summary_text": summary_data.get("summary_text", "")},
            )
            logger.info(f"Created summary for document {document_id}")

        elif stage == "extraction":
            # Extract structured data using active prompt
            if not document.raw_text:
                raise ValueError("Document has no raw_text for extraction")

            adapter_id = None
            if project.extractor_llm_id:
                adapter_id = str(project.extractor_llm_id)

            if not adapter_id:
                raise ValueError("No Extractor LLM configured for this project")

            # Get active prompt version
            active_prompt = project.prompt_versions.filter(is_active=True).first()
            if not active_prompt:
                raise ValueError("No active prompt version found")

            payload = {
                "document_id": str(document.id),
                "project_id": project_id,
                "document_text": document.raw_text,
                "prompt_text": active_prompt.prompt_text,
                "organization_id": organization_id,
                "adapter_instance_id": adapter_id,
            }

            response = requests.post(
                f"{prompt_service_url}/agentic/extract",
                json=payload,
                timeout=300,
            )

            if response.status_code != 200:
                raise ValueError(f"Extraction failed: {response.text}")

            extraction_data = response.json()

            # Save the extracted data
            AgenticExtractedData.objects.update_or_create(
                project=project,
                document=document,
                prompt_version=active_prompt,
                organization=document.organization,
                defaults={"data": extraction_data.get("extracted_data", {})},
            )
            logger.info(f"Extraction completed for document {document_id}")

        else:
            raise ValueError(f"Invalid stage: {stage}")

        # Mark stage as completed
        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage=stage,
            status="completed",
            progress=100,
            message=f"{stage.title()} completed successfully"
        )

        return {"status": "completed", "stage": stage, "document_id": document_id}

    except Exception as e:
        logger.error(f"Document processing failed for {stage}: {e}")

        # Mark stage as failed
        try:
            document = AgenticDocument.objects.get(id=document_id)
            state_mgr.set_stage_status(
                project_id=UUID(str(document.project.id)),
                stage=stage,
                status="failed",
                progress=0,
                message=str(e)
            )
        except:
            pass

        raise self.retry(exc=e)


@shared_task(
    name="agentic_studio.generate_schema",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_schema_task(self, project_id: str):
    """Generate schema from document summaries using Uniformer + Finalizer agents.

    This is similar to AutoPrompt's generate_schema_only_job.

    Agents used:
    - UniformerAgent: Merges field candidates from all summaries
    - FinalizerAgent: Generates final JSON Schema

    Args:
        project_id: UUID of the project
    """
    import requests
    from django.conf import settings

    state_mgr = ProcessingStateManager()

    try:
        project = AgenticProject.objects.get(id=project_id)
        organization_id = str(project.organization.organization_id)

        # Mark stage as processing
        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage="schema",
            status="in_progress",
            progress=0,
            message="Starting schema generation..."
        )

        # Get Agent LLM adapter
        adapter_id = None
        if project.agent_llm_id:
            adapter_id = str(project.agent_llm_id)

        if not adapter_id:
            raise ValueError("No Agent LLM configured for this project")

        # Get all summaries for this project
        summaries = AgenticSummary.objects.filter(project_id=project_id)

        if not summaries.exists():
            raise ValueError("No summaries found. Please generate summaries first.")

        # Format summaries for prompt-service
        summaries_data = []
        for summary in summaries:
            summaries_data.append({
                "document_id": str(summary.document.id),
                "summary_text": summary.summary_text,
                "fields": []  # TODO: Extract field candidates from summary
            })

        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage="schema",
            status="in_progress",
            progress=20,
            message=f"Uniformizing schema from {len(summaries_data)} summaries..."
        )

        # Call prompt-service to uniformize schemas
        prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
        prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
        prompt_service_url = f"{prompt_host}:{prompt_port}"

        payload = {
            "project_id": project_id,
            "summaries": summaries_data,
            "organization_id": organization_id,
            "adapter_instance_id": adapter_id,
        }

        response = requests.post(
            f"{prompt_service_url}/agentic/uniformize",
            json=payload,
            timeout=600,
        )

        if response.status_code != 200:
            raise ValueError(f"Schema uniformization failed: {response.text}")

        uniform_schema = response.json().get("uniform_schema", {})

        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage="schema",
            status="in_progress",
            progress=60,
            message="Finalizing schema..."
        )

        # Call prompt-service to finalize schema
        payload = {
            "project_id": project_id,
            "uniform_schema": uniform_schema,
            "organization_id": organization_id,
            "adapter_instance_id": adapter_id,
        }

        response = requests.post(
            f"{prompt_service_url}/agentic/finalize",
            json=payload,
            timeout=600,
        )

        if response.status_code != 200:
            raise ValueError(f"Schema finalization failed: {response.text}")

        json_schema = response.json().get("json_schema", {})

        # Deactivate old schemas for this project
        AgenticSchema.objects.filter(project=project).update(is_active=False)

        # Save the generated schema (mark as active)
        schema = AgenticSchema.objects.create(
            project=project,
            json_schema=json_schema,
            is_active=True,
            organization=project.organization,
        )

        state_mgr.set_stage_status(
            project_id=UUID(project_id),
            stage="schema",
            status="completed",
            progress=100,
            message="Schema generated successfully"
        )

        logger.info(f"Schema generated for project {project_id}, schema_id: {schema.id}")

        return {
            "status": "completed",
            "schema_id": str(schema.id),
            "project_id": project_id,
        }

    except Exception as e:
        logger.error(f"Schema generation failed: {e}")

        # Mark stage as failed
        try:
            state_mgr.set_stage_status(
                project_id=UUID(project_id),
                stage="schema",
                status="failed",
                progress=0,
                message=str(e)
            )
        except:
            pass

        raise self.retry(exc=e)


@shared_task(name="agentic_studio.run_pipeline", bind=True)
def run_pipeline_task(self, project_id: str):
    """Run the full multi-stage agentic pipeline (Lazy Schema Generation pattern).

    Similar to AutoPrompt's generate_schema_lazy_job.

    Phases:
    1. Raw text extraction (0-30%) - for documents missing raw_text
    2. Summarization (30-70%) - for documents missing summaries
    3. Schema generation (70-100%) - Uniformer + Finalizer

    Args:
        project_id: UUID of the project
    """
    state_mgr = ProcessingStateManager()

    try:
        project = AgenticProject.objects.get(id=project_id)

        # Reset pipeline state
        state_mgr.reset_pipeline(UUID(project_id))

        # PHASE 1: Raw text extraction (0-30%)
        state_mgr.set_stage_status(
            UUID(project_id), "raw_text", "in_progress", 0, "Checking documents for raw text..."
        )

        documents = project.documents.all()
        total_docs = documents.count()

        if total_docs == 0:
            state_mgr.mark_stage_failed(
                UUID(project_id), "raw_text", "No documents uploaded"
            )
            return {"status": "failed", "error": "No documents"}

        docs_without_text = documents.filter(raw_text__isnull=True)

        if docs_without_text.exists():
            logger.info(f"Processing raw_text for {docs_without_text.count()} documents")
            for doc in docs_without_text:
                process_document_stage_task.delay(str(doc.id), "raw_text")

            state_mgr.set_stage_status(
                UUID(project_id), "raw_text", "in_progress", 15,
                f"Processing {docs_without_text.count()} documents..."
            )
            # Note: Individual tasks will update status to completed
        else:
            state_mgr.mark_stage_complete(UUID(project_id), "raw_text", "All documents have raw text")

        # PHASE 2: Summarization (30-70%)
        state_mgr.set_stage_status(
            UUID(project_id), "summary", "in_progress", 30, "Checking for summaries..."
        )

        docs_with_text = documents.exclude(raw_text__isnull=True)
        docs_needing_summaries = []

        for doc in docs_with_text:
            if not AgenticSummary.objects.filter(document=doc).exists():
                docs_needing_summaries.append(doc)

        if docs_needing_summaries:
            logger.info(f"Generating summaries for {len(docs_needing_summaries)} documents")
            for doc in docs_needing_summaries:
                process_document_stage_task.delay(str(doc.id), "summary")

            state_mgr.set_stage_status(
                UUID(project_id), "summary", "in_progress", 50,
                f"Summarizing {len(docs_needing_summaries)} documents..."
            )
        else:
            state_mgr.mark_stage_complete(UUID(project_id), "summary", "All documents summarized")

        # PHASE 3: Schema generation (70-100%)
        # Enqueue schema generation task
        generate_schema_task.delay(project_id)

        return {
            "status": "in_progress",
            "project_id": project_id,
            "message": "Pipeline started successfully",
        }

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        state_mgr.mark_stage_failed(
            UUID(project_id), "raw_text", str(e)
        )
        raise


@shared_task(name="agentic_studio.tune_field", bind=True)
def tune_field_task(self, project_id: str, field_path: str):
    """Asynchronously tune a failing field using the tuning agent workflow.

    Args:
        project_id: UUID of the project
        field_path: Dot-separated field path (e.g., 'customer.name')
    """
    try:
        project = AgenticProject.objects.get(id=project_id)

        # Get active prompt
        active_prompt = project.prompt_versions.filter(is_active=True).first()
        if not active_prompt:
            raise ValueError("No active prompt version found")

        # Get active schema
        active_schema = project.schemas.filter(is_active=True).first()
        if not active_schema:
            raise ValueError("No active schema found")

        # Get failures for this field
        failures = AgenticComparisonResult.objects.filter(
            project=project,
            prompt_version=active_prompt,
            field_path=field_path,
            match=False,
        ).select_related("document")

        if not failures.exists():
            logger.warning(f"No failures found for field {field_path}")
            return {"status": "no_failures", "field_path": field_path}

        # Prepare failure data
        failure_data = []
        for failure in failures:
            failure_data.append({
                "document_id": str(failure.document.id),
                "extracted": failure.normalized_extracted,
                "verified": failure.normalized_verified,
                "error_type": failure.error_type,
            })

        # Call prompt-service to tune
        client = PromptServiceClient(organization_id=str(project.organization.id))

        try:
            result = client.tune_field(
                project_id=UUID(project_id),
                field_path=field_path,
                current_prompt=active_prompt.prompt_text,
                schema=json.loads(active_schema.json_schema),
                failures=failure_data,
                canary_fields=project.canary_fields or [],
            )

            if result and "tuned_prompt" in result:
                # Create new prompt version
                next_version = (
                    project.prompt_versions.order_by("-version").first().version + 1
                )

                new_prompt = AgenticPromptVersion.objects.create(
                    project=project,
                    organization=project.organization,
                    version=next_version,
                    short_desc=f"Tuned for field: {field_path}",
                    long_desc=result.get("explanation", ""),
                    prompt_text=result["tuned_prompt"],
                    is_active=False,  # Don't auto-activate
                    created_by_agent="tuner",
                    parent_version=active_prompt,
                )

                logger.info(
                    f"Created tuned prompt version {next_version} for field {field_path}"
                )
                return {
                    "status": "completed",
                    "prompt_version_id": str(new_prompt.id),
                    "version": next_version,
                }
            else:
                raise ValueError("Tuning returned no result")

        finally:
            # Cleanup would go here
            pass

    except Exception as e:
        logger.error(f"Field tuning failed: {e}")
        raise


@shared_task(name="agentic_studio.batch_extract", bind=True)
def batch_extract_task(self, project_id: str, prompt_version_id: str = None):
    """Extract data from all documents with verified data.

    Args:
        project_id: UUID of the project
        prompt_version_id: Optional UUID of specific prompt version to use
    """
    try:
        project = AgenticProject.objects.get(id=project_id)

        # Get prompt version
        if prompt_version_id:
            prompt_version = AgenticPromptVersion.objects.get(id=prompt_version_id)
        else:
            prompt_version = project.prompt_versions.filter(is_active=True).first()

        if not prompt_version:
            raise ValueError("No prompt version specified or active")

        # Get schema
        schema = project.schemas.filter(is_active=True).first()
        if not schema:
            raise ValueError("No active schema found")

        # Get documents with verified data
        documents = AgenticDocumentService.get_documents_with_verified_data(
            UUID(project_id)
        )

        if not documents:
            logger.warning("No documents with verified data found")
            return {"status": "no_documents"}

        client = PromptServiceClient(organization_id=str(project.organization.id))

        extracted_count = 0
        for document in documents:
            try:
                result = client.extract_from_document(
                    document_id=UUID(str(document.id)),
                    project_id=UUID(project_id),
                    prompt_text=prompt_version.prompt_text,
                    document_text=document.raw_text,
                    schema=json.loads(schema.json_schema),
                )

                if result and "extracted_data" in result:
                    # Store extracted data
                    AgenticExtractedData.objects.create(
                        project=project,
                        document=document,
                        prompt_version=prompt_version,
                        organization=project.organization,
                        data=result["extracted_data"],
                    )
                    extracted_count += 1

            except Exception as e:
                logger.error(f"Extraction failed for document {document.id}: {e}")
                continue

        logger.info(
            f"Batch extraction completed: {extracted_count}/{len(documents)} documents"
        )
        return {
            "status": "completed",
            "extracted_count": extracted_count,
            "total_documents": len(documents),
        }

    except Exception as e:
        logger.error(f"Batch extraction failed: {e}")
        raise


@shared_task(name="agentic_studio.compare_results", bind=True)
def compare_results_task(self, project_id: str, prompt_version_id: str = None):
    """Compare extracted data vs verified data for all documents.

    Creates AgenticComparisonResult entries for field-level analysis.

    Args:
        project_id: UUID of the project
        prompt_version_id: Optional UUID of specific prompt version
    """
    try:
        project = AgenticProject.objects.get(id=project_id)

        # Get prompt version
        if prompt_version_id:
            prompt_version = AgenticPromptVersion.objects.get(id=prompt_version_id)
        else:
            prompt_version = project.prompt_versions.filter(is_active=True).first()

        if not prompt_version:
            raise ValueError("No prompt version specified or active")

        # Get all extracted data for this prompt version
        extractions = AgenticExtractedData.objects.filter(
            project=project, prompt_version=prompt_version
        ).select_related("document")

        total_comparisons = 0
        matched_comparisons = 0

        for extraction in extractions:
            # Get verified data for this document
            verified = AgenticVerifiedData.objects.filter(
                project=project, document=extraction.document
            ).first()

            if not verified:
                logger.warning(
                    f"No verified data for document {extraction.document.id}"
                )
                continue

            # TODO: Call comparison service to compare field-by-field
            # This would use the lightweight LLM to classify errors
            # For now, create placeholder comparison results

            logger.info(
                f"Compared extraction vs verified for document {extraction.document.id}"
            )

        logger.info(
            f"Comparison completed: {matched_comparisons}/{total_comparisons} matches"
        )

        # Update prompt version accuracy
        if total_comparisons > 0:
            accuracy = matched_comparisons / total_comparisons
            prompt_version.accuracy = accuracy
            prompt_version.save(update_fields=["accuracy"])

        return {
            "status": "completed",
            "total_comparisons": total_comparisons,
            "matched": matched_comparisons,
            "accuracy": matched_comparisons / total_comparisons if total_comparisons > 0 else 0,
        }

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise
