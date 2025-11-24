"""Flask controller for Agentic Studio operations.

Provides endpoints for:
- Document summarization
- Schema generation (uniformize + finalize)
- Prompt generation
- Extraction
- Comparison
- Field tuning
"""

import asyncio
import json
import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from unstract.prompt_service.agents.agentic.critic_dryrunner import CriticDryRunnerAgent
from unstract.prompt_service.agents.agentic.finalizer import FinalizerAgent
from unstract.prompt_service.agents.agentic.pattern_miner import PatternMinerAgent
from unstract.prompt_service.agents.agentic.prompt_architect import (
    PromptArchitectAgent,
)
from unstract.prompt_service.agents.agentic.summarizer import SummarizerAgent
from unstract.prompt_service.agents.agentic.uniformer import UniformerAgent
from unstract.prompt_service.agents.agentic.verifier import VerifierAgent
from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge
from unstract.prompt_service.services.agentic.comparison_service import (
    ComparisonService,
)
from unstract.prompt_service.services.agentic.extraction_service import (
    ExtractionService,
)
from unstract.prompt_service.services.agentic.tuning_service import TuningService

logger = logging.getLogger(__name__)

# Create blueprint
agentic_bp = Blueprint("agentic", __name__, url_prefix="/agentic")


def get_llm_bridge(adapter_instance_id: str, organization_id: str, platform_api_key: str) -> UnstractAutogenBridge:
    """Create UnstractAutogenBridge for agent operations.

    Args:
        adapter_instance_id: UUID of the adapter instance
        organization_id: Organization ID for usage tracking
        platform_api_key: Platform API key from request headers

    Returns:
        UnstractAutogenBridge instance
    """
    return UnstractAutogenBridge(
        adapter_instance_id=adapter_instance_id,
        platform_api_key=platform_api_key,
        organization_id=organization_id,
    )


@agentic_bp.route("/summarize", methods=["POST"])
def summarize_document():
    """Summarize a document to extract field candidates.

    Request JSON:
    {
        "document_id": "uuid",
        "project_id": "uuid",
        "document_text": "...",
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"  # Optional, will be fetched from project
    }

    Response JSON:
    {
        "document_id": "uuid",
        "summary_text": "...",
        "fields": [...]
    }
    """
    try:
        data = request.get_json()

        document_id = data.get("document_id")
        project_id = data.get("project_id")
        document_text = data.get("document_text")
        organization_id = data.get("organization_id")
        adapter_instance_id = data.get("adapter_instance_id")

        if not all([document_id, project_id, document_text, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: document_id, project_id, document_text, organization_id"
                    }
                ),
                400,
            )

        # TODO: Fetch adapter_instance_id from project settings if not provided
        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create and run SummarizerAgent
        summarizer = SummarizerAgent(model_client=llm_bridge)
        result = asyncio.run(summarizer.summarize_document(document_text))

        return jsonify(
            {
                "document_id": document_id,
                "project_id": project_id,
                "summary_text": result["summary_text"],
                "fields": result.get("fields", []),
                "error": result.get("error"),
            }
        )

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/uniformize", methods=["POST"])
def uniformize_schemas():
    """Uniformize multiple document schemas.

    Request JSON:
    {
        "project_id": "uuid",
        "summaries": [
            {"document_id": "...", "fields": [...]},
            ...
        ],
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "uniform_schema": {...}
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        summaries = data.get("summaries", [])
        organization_id = data.get("organization_id")

        if not all([project_id, summaries, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, summaries, organization_id"
                    }
                ),
                400,
            )

        # Get adapter instance ID
        adapter_instance_id = data.get("adapter_instance_id")
        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create and run UniformerAgent
        uniformer = UniformerAgent(model_client=llm_bridge)
        result = asyncio.run(uniformer.uniformize_schemas(summaries))

        return jsonify(
            {
                "project_id": project_id,
                "uniform_schema": result,
            }
        )

    except Exception as e:
        logger.error(f"Schema uniformization failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/finalize", methods=["POST"])
def finalize_schema():
    """Finalize schema into JSON Schema format.

    Request JSON:
    {
        "project_id": "uuid",
        "uniform_schema": {...},
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "json_schema": {...}
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        uniform_schema = data.get("uniform_schema")
        organization_id = data.get("organization_id")

        if not all([project_id, uniform_schema, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, uniform_schema, organization_id"
                    }
                ),
                400,
            )

        # Get adapter instance ID
        adapter_instance_id = data.get("adapter_instance_id")
        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create and run FinalizerAgent
        finalizer = FinalizerAgent(model_client=llm_bridge)
        result = asyncio.run(finalizer.finalize_schema(uniform_schema))

        return jsonify(
            {
                "project_id": project_id,
                "json_schema": result,
            }
        )

    except Exception as e:
        logger.error(f"Schema finalization failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/generate-prompt", methods=["POST"])
def generate_prompt():
    """Generate initial extraction prompt from schema.

    Request JSON:
    {
        "project_id": "uuid",
        "schema": {...},
        "examples": [...],
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "prompt_text": "...",
        "metadata": {...}
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        schema = data.get("schema")
        organization_id = data.get("organization_id")

        if not all([project_id, schema, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, schema, organization_id"
                    }
                ),
                400,
            )

        # TODO: Implement PromptArchitectAgent
        logger.warning("generate_prompt not yet implemented - returning mock response")

        return jsonify(
            {
                "project_id": project_id,
                "prompt_text": "TODO: Generated prompt will appear here",
                "message": "TODO: Implement PromptArchitectAgent",
            }
        )

    except Exception as e:
        logger.error(f"Prompt generation failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/generate-prompt-pipeline", methods=["POST"])
def generate_prompt_pipeline():
    """Generate extraction prompt using 3-agent pipeline.

    This is the MAIN prompt generation endpoint that orchestrates:
    1. PatternMinerAgent - Mine extraction hints from documents
    2. PromptArchitectAgent - Draft 7-section extraction prompt
    3. CriticDryRunnerAgent - Test and refine the draft prompt

    Request JSON:
    {
        "project_id": "uuid",
        "schema": {...},
        "summaries": [{"summary_text": "..."}],
        "sample_documents": [{"raw_text": "...", "filename": "..."}],
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "prompt_text": "...",
        "pattern_hints": {...},
        "critique_results": {...},
        "short_desc": "...",
        "long_desc": "..."
    }
    """
    try:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken

        data = request.get_json()

        project_id = data.get("project_id")
        schema = data.get("schema")
        summaries = data.get("summaries", [])
        sample_documents = data.get("sample_documents", [])
        organization_id = data.get("organization_id")
        adapter_instance_id = data.get("adapter_instance_id")

        if not all([project_id, schema, organization_id, adapter_instance_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, schema, organization_id, adapter_instance_id"
                    }
                ),
                400,
            )

        if not summaries:
            return jsonify({"error": "At least one document summary is required"}), 400

        if not sample_documents:
            return jsonify({"error": "At least one sample document is required for dry-run testing"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # PHASE 1: PatternMiner (25-55%)
        logger.info(f"Phase 1: Running PatternMinerAgent for project {project_id}")

        pattern_miner = PatternMinerAgent(model_client=llm_bridge)

        # Prepare input for pattern miner
        pattern_input = f"""Schema:
{json.dumps(schema, indent=2)}

Document Summaries:
{json.dumps(summaries, indent=2)}

Sample Document (shortest):
{sample_documents[0].get('raw_text', '')[:5000]}
"""

        pattern_message = TextMessage(content=pattern_input, source="system")
        pattern_response = asyncio.run(pattern_miner.on_messages([pattern_message], CancellationToken()))

        pattern_hints_text = pattern_response.chat_message.content
        try:
            # Try to parse JSON from response
            pattern_hints = json.loads(pattern_hints_text)
        except json.JSONDecodeError:
            # If not valid JSON, extract JSON block
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', pattern_hints_text, re.DOTALL)
            if json_match:
                pattern_hints = json.loads(json_match.group(1))
            else:
                pattern_hints = {"raw_response": pattern_hints_text}

        logger.info(f"PatternMiner completed, extracted {len(pattern_hints.get('field_hints', {}))} field hints")

        # PHASE 2: PromptArchitect (55-80%)
        logger.info(f"Phase 2: Running PromptArchitectAgent for project {project_id}")

        architect = PromptArchitectAgent(model_client=llm_bridge)

        architect_input = f"""Generate an extraction prompt for the following schema and extraction hints.

Schema:
{json.dumps(schema, indent=2)}

Extraction Hints:
{json.dumps(pattern_hints, indent=2)}

Document Summaries:
{json.dumps(summaries, indent=2)}

Create a 7-section extraction prompt:
1. Task Overview
2. Output Schema
3. Per-Field Guidance
4. Formatting Rules
5. Examples (if applicable)
6. Edge Cases
7. Document (placeholder for {{{{DOCUMENT_TEXT}}}})
"""

        # Generate prompt using PromptArchitectAgent
        architect_message = TextMessage(content=architect_input, source="system")
        architect_response = asyncio.run(
            architect.agent.on_messages([architect_message], None)
        )
        draft_prompt = architect_response.chat_message.content

        logger.info(
            f"PromptArchitect completed, generated {len(draft_prompt)} character prompt"
        )

        # PHASE 3: CriticDryRunner (80-95%)
        logger.info(f"Phase 3: Running CriticDryRunnerAgent for project {project_id}")

        critic = CriticDryRunnerAgent(model_client=llm_bridge)

        critic_input = f"""Test and refine this draft extraction prompt.

Draft Prompt:
{draft_prompt}

Schema:
{json.dumps(schema, indent=2)}

Sample Document:
{sample_documents[0].get('raw_text', '')[:5000]}

Filename: {sample_documents[0].get('filename', 'sample.pdf')}

Test the prompt and suggest minimal, high-impact revisions if needed.
"""

        critic_message = TextMessage(content=critic_input, source="system")
        critic_response = asyncio.run(critic.on_messages([critic_message], CancellationToken()))

        critique_text = critic_response.chat_message.content

        # Try to parse critique JSON
        try:
            critique = json.loads(critique_text)
            final_prompt = critique.get("final_prompt_text", draft_prompt)
            test_passed = critique.get("test_passed", False)
        except json.JSONDecodeError:
            # If not valid JSON, try to extract JSON block
            import re
            # Try multiple patterns to find JSON
            json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', critique_text, re.DOTALL)
            if not json_match:
                # Try without markdown code block
                json_match = re.search(r'(\{[\s\S]*"final_prompt_text"[\s\S]*?\})', critique_text, re.DOTALL)

            if json_match:
                try:
                    critique = json.loads(json_match.group(1))
                    final_prompt = critique.get("final_prompt_text", draft_prompt)
                    test_passed = critique.get("test_passed", False)
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse extracted JSON: {e}")
                    critique = {"raw_response": critique_text, "parse_error": str(e)}
                    final_prompt = draft_prompt
                    test_passed = False
            else:
                # No JSON found, use draft prompt as fallback
                logger.warning("No JSON found in critique response, using draft prompt")
                critique = {"raw_response": critique_text}
                final_prompt = draft_prompt
                test_passed = False

        logger.info(f"CriticDryRunner completed, test_passed={test_passed}")

        # Generate short and long descriptions
        short_desc = f"Auto-generated prompt v1"
        long_desc = f"Generated using 3-agent pipeline (PatternMiner → PromptArchitect → CriticDryRunner). Test passed: {test_passed}"

        return jsonify(
            {
                "project_id": project_id,
                "prompt_text": final_prompt,
                "pattern_hints": pattern_hints,
                "critique_results": critique,
                "short_desc": short_desc,
                "long_desc": long_desc,
            }
        )

    except Exception as e:
        logger.error(f"3-agent prompt pipeline failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/extract", methods=["POST"])
def extract_from_document():
    """Extract data from document using a prompt.

    Request JSON:
    {
        "document_id": "uuid",
        "project_id": "uuid",
        "prompt_text": "...",
        "document_text": "...",
        "schema": {...},
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "document_id": "uuid",
        "extracted_data": {...}
    }
    """
    try:
        data = request.get_json()

        document_id = data.get("document_id")
        prompt_text = data.get("prompt_text")
        document_text = data.get("document_text")
        json_schema = data.get("schema", {})
        organization_id = data.get("organization_id")
        adapter_instance_id = data.get("adapter_instance_id")

        if not all([document_id, prompt_text, document_text, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: document_id, prompt_text, document_text, organization_id"
                    }
                ),
                400,
            )

        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create and use ExtractionService
        extraction_service = ExtractionService(llm_bridge)
        result = asyncio.run(extraction_service.extract_from_document(
            document_text=document_text,
            prompt_text=prompt_text,
            json_schema=json_schema,
            document_id=document_id,
        ))

        return jsonify(
            {
                "document_id": document_id,
                "extracted_data": result["extracted_data"],
                "raw_response": result["raw_response"],
                "validation_errors": result["validation_errors"],
                "metadata": result["metadata"],
            }
        )

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/compare", methods=["POST"])
def compare_results():
    """Compare extracted data vs verified data.

    Request JSON:
    {
        "project_id": "uuid",
        "extracted_data": {...},
        "verified_data": {...},
        "organization_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "comparison_results": [...]
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        document_id = data.get("document_id")
        extracted_data = data.get("extracted_data")
        verified_data = data.get("verified_data")
        use_llm_classification = data.get("use_llm_classification", False)
        lightweight_llm_adapter = data.get("lightweight_llm_adapter")
        organization_id = data.get("organization_id")

        if not all([project_id, extracted_data, verified_data]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, extracted_data, verified_data"
                    }
                ),
                400,
            )

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create lightweight LLM bridge if needed for error classification
        lightweight_llm = None
        if use_llm_classification and lightweight_llm_adapter and organization_id:
            lightweight_llm = get_llm_bridge(lightweight_llm_adapter, organization_id, platform_key)

        # Create and use ComparisonService
        comparison_service = ComparisonService(lightweight_llm)
        result = asyncio.run(comparison_service.compare_data(
            extracted_data=extracted_data,
            verified_data=verified_data,
            document_id=document_id,
            use_llm_classification=use_llm_classification,
        ))

        return jsonify(
            {
                "project_id": project_id,
                "document_id": result["document_id"],
                "total_fields": result["total_fields"],
                "matched_fields": result["matched_fields"],
                "failed_fields": result["failed_fields"],
                "accuracy": result["accuracy"],
                "field_results": result["field_results"],
                "error_distribution": result["error_distribution"],
            }
        )

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/tune-field", methods=["POST"])
def tune_field():
    """Tune extraction prompt for a specific failing field.

    Request JSON:
    {
        "project_id": "uuid",
        "field_path": "customer.name",
        "current_prompt": "...",
        "schema": {...},
        "failures": [...],
        "canary_fields": [...],
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "field_path": "customer.name",
        "tuned_prompt": "...",
        "explanation": "..."
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        field_path = data.get("field_path")
        current_prompt = data.get("current_prompt")
        failures = data.get("failures", [])
        schema = data.get("schema", {})
        canary_fields = data.get("canary_fields", [])
        test_documents = data.get("test_documents")
        error_type = data.get("error_type")
        organization_id = data.get("organization_id")
        adapter_instance_id = data.get("adapter_instance_id")

        if not all([project_id, field_path, current_prompt, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, field_path, "
                        "current_prompt, organization_id"
                    }
                ),
                400,
            )

        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create TuningService
        tuning_service = TuningService(llm_bridge)

        # Run the tuning workflow
        result = asyncio.run(tuning_service.tune_field(
            current_prompt=current_prompt,
            field_path=field_path,
            failures=failures,
            schema=schema,
            canary_fields=canary_fields if canary_fields else None,
            test_documents=test_documents,
            error_type=error_type,
        ))

        # Build response
        response = {
            "project_id": project_id,
            "field_path": field_path,
            "success": result.get("success", False),
            "tuned_prompt": result.get("tuned_prompt"),
            "explanation": result.get("reasoning"),
            "iterations": result.get("iterations", 0),
            "metrics": result.get("metrics", {}),
        }

        # Include workflow details if available
        if "workflow_stages" in result:
            response["workflow_stages"] = {
                "edit_attempts": len(result["workflow_stages"].get("edit_attempts", [])),
                "critic_reviews": len(result["workflow_stages"].get("critic_reviews", [])),
                "guard_tests": len(result["workflow_stages"].get("guard_tests", [])),
                "dry_runs": len(result["workflow_stages"].get("dry_runs", [])),
            }

        if "edit_details" in result:
            response["edit_details"] = {
                "edit_type": result["edit_details"].get("edit_type"),
                "target_section": result["edit_details"].get("target_section"),
                "reasoning": result["edit_details"].get("reasoning"),
            }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Field tuning failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/run-pipeline", methods=["POST"])
def run_full_pipeline():
    """Run the full agentic pipeline (orchestration endpoint).

    Request JSON:
    {
        "project_id": "uuid",
        "organization_id": "uuid"
    }

    Response JSON:
    {
        "project_id": "uuid",
        "status": "started",
        "message": "..."
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        organization_id = data.get("organization_id")

        if not all([project_id, organization_id]):
            return (
                jsonify(
                    {"error": "Missing required fields: project_id, organization_id"}
                ),
                400,
            )

        # TODO: Implement full pipeline orchestration
        logger.warning("run_full_pipeline not yet implemented - returning mock response")

        return jsonify(
            {
                "project_id": project_id,
                "status": "started",
                "message": "TODO: Implement full pipeline orchestration",
            }
        )

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/extract-text", methods=["POST"])
def extract_text():
    """Extract raw text from a document using X2Text adapter.

    This wraps the existing ExtractionService for agentic workflows.

    Request JSON:
    {
        "document_id": "uuid",
        "project_id": "uuid",
        "file_path": "organizations/.../file.pdf",
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"  # X2Text/LLMWhisperer adapter
    }

    Response JSON:
    {
        "document_id": "uuid",
        "raw_text": "..."
    }

    Note: Pages are extracted during upload via PyPDF2, not returned here.
    """
    try:
        from unstract.prompt_service.services.extraction import ExtractionService
        from unstract.prompt_service.constants import ExecutionSource

        data = request.get_json()

        document_id = data.get("document_id")
        project_id = data.get("project_id")
        file_path = data.get("file_path")
        organization_id = data.get("organization_id")
        adapter_instance_id = data.get("adapter_instance_id")
        output_file_path = data.get("output_file_path")  # Optional: where to write extracted text

        if not all([document_id, project_id, file_path, organization_id, adapter_instance_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: document_id, project_id, file_path, organization_id, adapter_instance_id"
                    }
                ),
                400,
            )

        # Get platform key from headers (required by ExtractionService)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Use existing extraction service (handles X2Text instantiation correctly)
        # If output_file_path is provided, X2Text will write the file automatically
        extracted_text = ExtractionService.perform_extraction(
            x2text_instance_id=adapter_instance_id,
            file_path=file_path,
            run_id=document_id,  # Use document_id as run_id for tracking
            platform_key=platform_key,
            output_file_path=output_file_path,  # X2Text writes file here (like old prompt studio)
            enable_highlight=False,
            usage_kwargs={"file_name": file_path.split("/")[-1]},
            tags=None,
            execution_source=ExecutionSource.IDE.value,
            tool_exec_metadata=None,
            execution_run_data_folder=None,
        )

        return jsonify(
            {
                "document_id": document_id,
                "project_id": project_id,
                "raw_text": extracted_text,
            }
        )

    except Exception as e:
        logger.error(f"Text extraction failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/generate-verified", methods=["POST"])
def generate_verified():
    """Generate verified ground truth data from extracted data.

    Request JSON:
    {
        "project_id": "uuid",
        "document_id": "uuid",
        "document_text": "raw text...",
        "extracted_data": {...},
        "schema": {...},  # optional
        "organization_id": "uuid",
        "adapter_instance_id": "uuid"
    }

    Response JSON:
    {
        "document_id": "uuid",
        "project_id": "uuid",
        "data": {...},  # Verified field values
        "verification_notes": "..."
    }
    """
    try:
        data = request.get_json()

        project_id = data.get("project_id")
        document_id = data.get("document_id")
        document_text = data.get("document_text")
        extracted_data = data.get("extracted_data")
        schema = data.get("schema")
        organization_id = data.get("organization_id")

        if not all([project_id, document_id, document_text, extracted_data, organization_id]):
            return (
                jsonify(
                    {
                        "error": "Missing required fields: project_id, document_id, document_text, extracted_data, organization_id"
                    }
                ),
                400,
            )

        # Get adapter instance ID
        adapter_instance_id = data.get("adapter_instance_id")
        if not adapter_instance_id:
            return jsonify({"error": "adapter_instance_id is required"}), 400

        # Get platform key from headers (required for SDK authentication)
        platform_key = request.headers.get("X-Platform-Key", "")

        # Create LLM bridge
        llm_bridge = get_llm_bridge(adapter_instance_id, organization_id, platform_key)

        # Create and run VerifierAgent
        verifier = VerifierAgent(model_client=llm_bridge)
        result = asyncio.run(
            verifier.generate_verified_data(
                document_text=document_text,
                extracted_data=extracted_data,
                schema=schema,
            )
        )

        return jsonify(
            {
                "document_id": document_id,
                "project_id": project_id,
                "data": result.get("data", {}),
                "verification_notes": result.get("verification_notes", ""),
                "error": result.get("error"),
            }
        )

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/summary", methods=["GET"])
def get_analytics_summary(project_id):
    """Get analytics summary for a project.

    This endpoint provides high-level statistics including:
    - Total documents compared
    - Total fields compared
    - Matched vs failed fields
    - Overall accuracy percentage

    Response JSON:
    {
        "total_docs": int,
        "total_fields": int,
        "matched_fields": int,
        "failed_fields": int,
        "overall_accuracy": float
    }
    """
    try:
        # TODO: Fetch comparison results from database/storage
        # For now, return mock data structure
        return jsonify({
            "total_docs": 0,
            "total_fields": 0,
            "matched_fields": 0,
            "failed_fields": 0,
            "overall_accuracy": 0.0
        })
    except Exception as e:
        logger.error(f"Failed to get analytics summary for project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/top-mismatches", methods=["GET"])
def get_top_mismatched_fields(project_id):
    """Get top mismatched fields for a project.

    Query params:
    - limit: Number of fields to return (default: 10)

    Response JSON: Array of
    {
        "field_path": str,
        "accuracy": float,
        "incorrect": int,
        "common_error": str | null
    }
    """
    try:
        limit = request.args.get("limit", 10, type=int)

        # TODO: Fetch field-level statistics from database/storage
        # For now, return empty array
        return jsonify([])
    except Exception as e:
        logger.error(f"Failed to get top mismatched fields for project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/category-breakdown", methods=["GET"])
def get_category_breakdown(project_id):
    """Get category breakdown for a project.

    Response JSON: Array of
    {
        "category": str,  # "Header", "LineItems", "Totals", "Other"
        "total_fields": int,
        "avg_accuracy": float
    }
    """
    try:
        # TODO: Implement category inference and aggregation
        # For now, return empty array
        return jsonify([])
    except Exception as e:
        logger.error(f"Failed to get category breakdown for project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/error-types", methods=["GET"])
def get_error_type_distribution(project_id):
    """Get error type distribution for a project.

    Response JSON: Array of
    {
        "error_type": str,  # "truncation", "format", "missing", "minor", "major"
        "count": int
    }
    """
    try:
        # TODO: Aggregate error types from comparison results
        # For now, return empty array
        return jsonify([])
    except Exception as e:
        logger.error(f"Failed to get error type distribution for project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/field/<path:field_path>", methods=["GET"])
def get_field_detail(project_id, field_path):
    """Get detailed analytics for a specific field.

    Response JSON:
    {
        "field_path": str,
        "accuracy": float,
        "mismatches": [
            {
                "doc_name": str,
                "verified": str,
                "extracted": str,
                "error_type": str | null
            }
        ]
    }
    """
    try:
        # TODO: Fetch field-specific comparison results
        # For now, return empty structure
        return jsonify({
            "field_path": field_path,
            "accuracy": 100.0,
            "mismatches": []
        })
    except Exception as e:
        logger.error(f"Failed to get field detail for {field_path} in project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/projects/<project_id>/analytics/matrix", methods=["GET"])
def get_mismatch_matrix(project_id):
    """Get mismatch matrix data for heatmap visualization.

    Response JSON:
    {
        "docs": [{"id": str, "name": str}],
        "fields": [{"path": str}],
        "data": [
            {
                "doc_id": str,
                "field_path": str,
                "status": str  # "match", "partial", "mismatch"
            }
        ]
    }
    """
    try:
        # TODO: Build matrix from comparison results
        # For now, return empty structure
        return jsonify({
            "docs": [],
            "fields": [],
            "data": []
        })
    except Exception as e:
        logger.error(f"Failed to get mismatch matrix for project {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


@agentic_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint.

    Response JSON:
    {
        "status": "healthy",
        "service": "agentic-studio"
    }
    """
    return jsonify({"status": "healthy", "service": "agentic-studio"})
