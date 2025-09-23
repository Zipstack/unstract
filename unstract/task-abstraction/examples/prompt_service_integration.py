"""Example integration showing workflow-based architecture replacing Prompt Studio service.

This demonstrates how to eliminate the Flask Prompt Studio service by converting
its logic into helper functions that workflows call directly, achieving complete
service consolidation and decoupling from backend dependencies.
"""

import asyncio
import logging
from typing import Optional

from unstract.task_abstraction import (
    get_task_client, 
    workflow, 
    task,
    BaseWorkflow,
    TaskContext
)
from unstract.task_abstraction.registry import register_service_workflows

# Import helper functions instead of service calls
from unstract.prompt_helpers import (
    ExtractionHelper,
    ChunkingHelper,
    LLMHelper,
    EvaluationHelper,
    FormattingHelper,
    TextExtractionConfig,
    ChunkingConfig,
    LLMConfig
)

logger = logging.getLogger(__name__)

# Redesigned workflow using helper functions instead of Prompt Studio service
@workflow(
    name="document-processing-pipeline",
    description="6-stage document processing using helper functions",
    timeout_minutes=30,
    version="2.0.0"  # Helper-based version
)
class DocumentProcessingWorkflow(BaseWorkflow):
    """Main document processing workflow using decoupled helper functions."""
    
    @task(name="validate-input", timeout_minutes=2)
    def validate_input(self, input_data: dict, ctx: TaskContext) -> dict:
        """Validate input document and parameters using helper."""
        document_path = input_data.get("document_path")
        if not document_path:
            raise ValueError("Document path is required")
        
        # Use helper function instead of Flask validation
        extraction_helper = ExtractionHelper()
        validation_result = extraction_helper.validate_document(document_path)
        
        return {
            "document_path": document_path,
            "validation_status": "passed" if validation_result.is_valid else "failed",
            "document_type": validation_result.document_type,
            "file_size": validation_result.file_size_mb
        }
    
    @task(name="extract-text", parents=["validate-input"], timeout_minutes=10)
    def extract_text(self, input_data: dict, ctx: TaskContext) -> dict:
        """Extract text using helper function instead of service call."""
        validated = ctx.task_output("validate-input")
        document_path = validated["document_path"]
        
        # Use extraction helper directly - NO service calls
        config = TextExtractionConfig(
            x2text_instance_id=input_data.get("x2text_instance_id"),
            enable_ocr=True,
            preserve_formatting=True
        )
        
        extraction_helper = ExtractionHelper(config)
        result = extraction_helper.extract_text_from_file(document_path)
        
        return {
            "text": result.extracted_text,
            "page_count": result.page_count,
            "character_count": result.character_count,
            "extraction_method": result.extraction_method,
            "confidence_score": result.confidence_score
        }
    
    @task(name="chunk-text", parents=["extract-text"], timeout_minutes=5)
    def chunk_text(self, input_data: dict, ctx: TaskContext) -> dict:
        """Chunk text using helper function."""
        text_data = ctx.task_output("extract-text")
        text = text_data["text"]
        
        # Use chunking helper directly
        config = ChunkingConfig(
            strategy="smart",  # Context-aware chunking
            chunk_size=input_data.get("chunk_size", 1000),
            chunk_overlap=input_data.get("chunk_overlap", 100)
        )
        
        chunking_helper = ChunkingHelper(config)
        result = chunking_helper.chunk_text(text)
        
        return {
            "chunks": result.chunks,
            "total_chunks": result.chunk_count,
            "chunking_strategy": result.chunking_strategy.value,
            "total_characters": result.total_characters
        }
    
    @task(name="process-llm", parents=["chunk-text"], timeout_minutes=15)
    def process_llm(self, input_data: dict, ctx: TaskContext) -> dict:
        """Process chunks through LLM using helper function."""
        chunks_data = ctx.task_output("chunk-text")
        chunks = chunks_data["chunks"]
        
        # Use LLM helper directly - NO Prompt Studio service
        llm_config = LLMConfig(
            adapter_instance_id=input_data.get("llm_adapter_id"),
            temperature=0.1,
            max_tokens=4000
        )
        
        llm_helper = LLMHelper(
            adapter_instance_id=input_data.get("llm_adapter_id"),
            config=llm_config
        )
        
        # Process each output configuration
        processed_results = {}
        for output_config in input_data.get("outputs", []):
            prompt = output_config["prompt"]
            
            # Process prompt for each chunk and aggregate
            chunk_results = []
            for i, chunk in enumerate(chunks):
                result = llm_helper.process_prompt(
                    prompt,
                    context={"text": chunk, "chunk_id": i}
                )
                chunk_results.append({
                    "chunk_id": i,
                    "response": result.response,
                    "tokens_used": result.tokens_used,
                    "confidence": 0.95  # Could be calculated
                })
            
            processed_results[output_config["name"]] = {
                "chunks": chunk_results,
                "total_chunks": len(chunk_results),
                "prompt_used": prompt
            }
        
        return {
            "processed_results": processed_results,
            "total_outputs": len(processed_results)
        }
    
    @task(name="evaluate-results", parents=["process-llm"], timeout_minutes=5)
    def evaluate_results(self, input_data: dict, ctx: TaskContext) -> dict:
        """Evaluate results using helper functions."""
        llm_data = ctx.task_output("process-llm")
        processed_results = llm_data["processed_results"]
        
        # Use evaluation helper for quality, security, guidance checks
        evaluation_helper = EvaluationHelper()
        
        evaluation_results = {}
        for output_name, result_data in processed_results.items():
            output_config = next(
                o for o in input_data.get("outputs", []) 
                if o["name"] == output_name
            )
            
            eval_settings = output_config.get("eval_settings", {})
            if not eval_settings.get("evaluate", False):
                continue
            
            # Combine chunk responses for evaluation
            combined_response = " ".join(
                chunk["response"] for chunk in result_data["chunks"]
            )
            
            # Quality evaluations
            if eval_settings.get("eval_quality_faithfulness"):
                faithfulness = evaluation_helper.evaluate_faithfulness(
                    combined_response, 
                    input_data.get("source_context", "")
                )
                evaluation_results[f"{output_name}_faithfulness"] = faithfulness.score
            
            # Security evaluations
            if eval_settings.get("eval_security_pii"):
                pii_result = evaluation_helper.detect_pii(combined_response)
                evaluation_results[f"{output_name}_pii_detected"] = pii_result.passed
        
        return {
            "evaluation_results": evaluation_results,
            "processed_results": processed_results
        }
    
    @task(name="format-output", parents=["evaluate-results"], timeout_minutes=3)
    def format_output(self, input_data: dict, ctx: TaskContext) -> dict:
        """Format and store final output using helper."""
        eval_data = ctx.task_output("evaluate-results")
        
        # Use formatting helper for output processing
        formatter = FormattingHelper()
        
        final_output = {}
        for output_config in input_data.get("outputs", []):
            output_name = output_config["name"]
            output_type = output_config.get("type", "text")
            
            if output_name in eval_data["processed_results"]:
                raw_result = eval_data["processed_results"][output_name]
                
                # Format based on output type
                formatted = formatter.format_output(
                    raw_result["chunks"],
                    output_type=output_type,
                    enforce_type=output_config.get("enforce_type", True)
                )
                
                final_output[output_name] = {
                    "value": formatted.result,
                    "type": output_type,
                    "confidence": 0.95,
                    "evaluation_scores": {
                        k: v for k, v in eval_data["evaluation_results"].items()
                        if k.startswith(output_name)
                    }
                }
        
        return {
            "status": "completed",
            "final_output": final_output,
            "processing_summary": {
                "total_outputs": len(final_output),
                "document_id": ctx.workflow_id,
                "processing_time_ms": ctx.get_total_processing_time()
            }
        }


@workflow(name="llm-interaction", description="Direct LLM interaction workflow")
class LLMInteractionWorkflow(BaseWorkflow):
    """Workflow for direct LLM interactions (chat, completion, etc.)."""
    
    @task(name="prepare-prompt")
    def prepare_prompt(self, input_data: dict, ctx: TaskContext) -> dict:
        """Prepare and validate LLM prompt."""
        prompt = input_data.get("prompt", "")
        model = input_data.get("model", "gpt-3.5-turbo")
        
        return {
            "prepared_prompt": prompt,
            "model": model,
            "parameters": {"temperature": 0.7, "max_tokens": 1000}
        }
    
    @task(name="call-llm", parents=["prepare-prompt"])
    def call_llm(self, input_data: dict, ctx: TaskContext) -> dict:
        """Make LLM API call."""
        prompt_data = ctx.task_output("prepare-prompt")
        
        # Use existing LLM adapter logic
        response = f"LLM response to: {prompt_data['prepared_prompt'][:50]}..."
        
        return {
            "response": response,
            "model_used": prompt_data["model"],
            "tokens_used": 150,
            "response_time": 2.5
        }


# Service initialization for Prompt Service
async def initialize_prompt_service_workflows(
    backend_override: Optional[str] = None
) -> dict:
    """Initialize Prompt Service workflows.
    
    This function should be called during Prompt Service startup
    to register all workflows with the abstraction layer.
    
    Args:
        backend_override: Optional backend type override
        
    Returns:
        Registration summary
    """
    logger.info("Initializing Prompt Service workflows...")
    
    # Register workflows
    summary = await register_service_workflows(
        service_name="prompt-service",
        workflow_packages=[
            "unstract.prompt_service.workflows",  # Main workflows
            "unstract.prompt_service.processors", # Processing workflows
        ]
    )
    
    logger.info(f"Prompt Service workflow initialization complete: {summary}")
    return summary


# Flask app integration example
def create_prompt_service_app():
    """Example Flask app factory with workflow registration."""
    from flask import Flask
    
    app = Flask(__name__)
    
    # Store initialization task to run when event loop is available
    app.workflow_init_task = initialize_prompt_service_workflows
    
    @app.route("/api/v2/process-document", methods=["POST"])
    async def process_document():
        """New API endpoint using workflow abstraction."""
        from flask import request, jsonify
        
        # Get task client
        client = get_task_client()
        if not client.is_started:
            await client.startup()
        
        # Start workflow
        input_data = request.get_json()
        result = await client.run_workflow(
            "document-processing-pipeline",
            input_data
        )
        
        return jsonify({
            "workflow_id": result.workflow_id,
            "status": result.status.value,
            "result": result.task_results.get("store-results", {}).get("result")
        })
    
    @app.route("/api/v2/llm-chat", methods=["POST"])
    async def llm_chat():
        """New LLM interaction endpoint."""
        from flask import request, jsonify
        
        client = get_task_client()
        if not client.is_started:
            await client.startup()
        
        input_data = request.get_json()
        result = await client.run_workflow("llm-interaction", input_data)
        
        return jsonify({
            "workflow_id": result.workflow_id,
            "response": result.task_results.get("call-llm", {}).get("result", {}).get("response")
        })
    
    return app


# Migration helper for existing Celery tasks
@workflow(name="celery-bridge", description="Bridge for calling existing Celery tasks")
class CeleryBridgeWorkflow(BaseWorkflow):
    """Workflow to bridge between new abstraction and existing Celery tasks."""
    
    @task(name="call-legacy-task")
    def call_legacy_celery_task(self, input_data: dict, ctx: TaskContext) -> dict:
        """Call existing Celery task during migration period."""
        task_name = input_data.get("celery_task_name")
        task_args = input_data.get("task_args", [])
        task_kwargs = input_data.get("task_kwargs", {})
        
        # Import and call existing Celery task
        try:
            from celery import current_app
            task = current_app.tasks.get(task_name)
            if task:
                result = task.apply_async(args=task_args, kwargs=task_kwargs)
                return {"celery_result": result.get(), "status": "success"}
            else:
                return {"error": f"Celery task {task_name} not found", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}


# CLI for Prompt Service workflow management
async def cli_prompt_service():
    """CLI helper for Prompt Service workflow operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Prompt Service Workflow CLI")
    parser.add_argument("--action", choices=["register", "test", "status"], required=True)
    parser.add_argument("--backend", help="Backend override")
    
    args = parser.parse_args()
    
    if args.action == "register":
        await initialize_prompt_service_workflows(args.backend)
    elif args.action == "test":
        # Test workflow execution
        client = get_task_client(backend_override=args.backend)
        await client.startup()
        
        test_result = await client.run_workflow(
            "document-processing-pipeline",
            {"document_path": "/test/doc.pdf"}
        )
        print(f"Test result: {test_result.status}")
        
    elif args.action == "status":
        # Check workflow registration status
        client = get_task_client(backend_override=args.backend)
        workflows = client.get_registered_workflows()
        print(f"Registered workflows: {workflows}")


if __name__ == "__main__":
    asyncio.run(cli_prompt_service())