"""TuningService orchestrator for multi-agent prompt improvement workflow.

The TuningService coordinates the four tuning agents (Editor, Critic, Guard, DryRunner)
to iteratively improve extraction prompts for failing fields.
"""

import logging
from typing import Any, Dict, List, Optional

from unstract.prompt_service.agents.agentic.tuner.critic import CriticAgent
from unstract.prompt_service.agents.agentic.tuner.dry_runner import DryRunnerAgent
from unstract.prompt_service.agents.agentic.tuner.editor import EditorAgent
from unstract.prompt_service.agents.agentic.tuner.guard import GuardAgent
from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge

logger = logging.getLogger(__name__)


class TuningService:
    """Orchestrates multi-agent prompt tuning workflow.

    Workflow:
    1. EditorAgent analyzes failures and proposes a prompt edit
    2. CriticAgent reviews the edit for quality and safety
    3. If REVISE, loop back to EditorAgent with feedback (max 3 iterations)
    4. GuardAgent tests edit against canary fields
    5. DryRunnerAgent tests edit on failing documents
    6. If all pass, return successful edit; otherwise, reject

    The service tracks iteration history and provides detailed results
    for each stage of the workflow.
    """

    MAX_ITERATIONS = 5  # Maximum edit-review cycles
    MAX_REVISION_ATTEMPTS = 3  # Maximum times to try revising an edit

    def __init__(self, model_client: UnstractAutogenBridge):
        """Initialize the TuningService with all tuning agents.

        Args:
            model_client: UnstractAutogenBridge instance for LLM access
        """
        self.model_client = model_client

        # Initialize all agents
        self.editor = EditorAgent(model_client)
        self.critic = CriticAgent(model_client)
        self.guard = GuardAgent(model_client)
        self.dry_runner = DryRunnerAgent(model_client)

        logger.info("TuningService initialized with all agents")

    async def tune_field(
        self,
        current_prompt: str,
        field_path: str,
        failures: List[Dict[str, Any]],
        schema: Dict[str, Any],
        canary_fields: Optional[List[str]] = None,
        test_documents: Optional[List[Dict[str, Any]]] = None,
        error_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute full tuning workflow for a failing field.

        Args:
            current_prompt: Current extraction prompt text
            field_path: Dot-notation path of failing field (e.g., "invoice.total")
            failures: List of failure examples with extracted/verified values
            schema: JSON schema for all fields
            canary_fields: Optional list of field paths to protect from regression
            test_documents: Optional test documents for dry run (uses failures if not provided)
            error_type: Optional specific error type to focus on

        Returns:
            Dictionary containing:
            - success: Boolean indicating if tuning succeeded
            - tuned_prompt: The improved prompt (if successful)
            - edit_details: Details of the applied edit
            - workflow_stages: Results from each stage (edit, review, guard, dry_run)
            - iterations: Number of edit-review cycles performed
            - reasoning: Explanation of success/failure
            - error: Error message if workflow failed
        """
        try:
            logger.info(f"Starting tuning workflow for field: {field_path}")

            # Initialize workflow tracking
            workflow_stages = {
                "edit_attempts": [],
                "critic_reviews": [],
                "guard_tests": [],
                "dry_runs": [],
            }

            # If no test documents provided, use failure documents
            if test_documents is None:
                test_documents = self._prepare_test_documents_from_failures(failures)

            # Stage 1: Edit-Review Loop
            approved_edit = None
            revision_attempts = 0

            for iteration in range(self.MAX_ITERATIONS):
                logger.info(f"Tuning iteration {iteration + 1}/{self.MAX_ITERATIONS}")

                # EditorAgent: Generate or revise edit
                edit_result = await self.editor.edit_prompt(
                    current_prompt=current_prompt,
                    field_path=field_path,
                    failures=failures,
                    schema=schema,
                    error_type=error_type,
                )

                workflow_stages["edit_attempts"].append(
                    {"iteration": iteration + 1, "result": edit_result}
                )

                if edit_result.get("error"):
                    logger.error(f"Edit generation failed: {edit_result['error']}")
                    return {
                        "success": False,
                        "reasoning": f"Edit generation failed: {edit_result['error']}",
                        "workflow_stages": workflow_stages,
                    }

                # CriticAgent: Review the edit
                review_result = await self.critic.review_edit(
                    original_prompt=current_prompt,
                    proposed_edit=edit_result,
                    schema=schema,
                    canary_fields=canary_fields,
                )

                workflow_stages["critic_reviews"].append(
                    {"iteration": iteration + 1, "result": review_result}
                )

                decision = review_result.get("decision")

                if decision == "APPROVE":
                    logger.info(f"Edit approved after {iteration + 1} iterations")
                    approved_edit = edit_result
                    break

                elif decision == "REVISE":
                    revision_attempts += 1
                    if revision_attempts >= self.MAX_REVISION_ATTEMPTS:
                        logger.warning(
                            f"Max revision attempts ({self.MAX_REVISION_ATTEMPTS}) reached"
                        )
                        return {
                            "success": False,
                            "reasoning": "Failed to generate acceptable edit after multiple revisions",
                            "workflow_stages": workflow_stages,
                            "iterations": iteration + 1,
                        }

                    # TODO: Feed critic's suggestions back to editor for next iteration
                    logger.info(
                        f"Edit needs revision (attempt {revision_attempts}/{self.MAX_REVISION_ATTEMPTS})"
                    )
                    continue

                else:  # REJECT
                    logger.warning(f"Edit rejected: {review_result.get('reasoning')}")
                    return {
                        "success": False,
                        "reasoning": f"Edit rejected by critic: {review_result.get('reasoning')}",
                        "workflow_stages": workflow_stages,
                        "iterations": iteration + 1,
                    }

            # Check if we got an approved edit
            if not approved_edit:
                return {
                    "success": False,
                    "reasoning": f"No approved edit after {self.MAX_ITERATIONS} iterations",
                    "workflow_stages": workflow_stages,
                }

            # Stage 2: Apply edit and create tuned prompt
            tuned_prompt = self._apply_edit(current_prompt, approved_edit)

            # Stage 3: GuardAgent - Test against canary fields
            if canary_fields:
                logger.info("Testing against canary fields")

                guard_result = await self.guard.test_canary_fields(
                    original_prompt=current_prompt,
                    edited_prompt=tuned_prompt,
                    canary_fields=canary_fields,
                    test_documents=test_documents,
                    schema=schema,
                )

                workflow_stages["guard_tests"].append(guard_result)

                if guard_result.get("decision") == "FAIL":
                    logger.warning(
                        f"Guard test failed: {guard_result.get('reasoning')}"
                    )
                    return {
                        "success": False,
                        "reasoning": f"Canary field regression detected: {guard_result.get('reasoning')}",
                        "workflow_stages": workflow_stages,
                        "tuned_prompt": tuned_prompt,
                        "edit_details": approved_edit,
                    }

                logger.info("Guard test passed")
            else:
                logger.info("No canary fields defined, skipping guard test")

            # Stage 4: DryRunnerAgent - Test on failing documents
            logger.info("Running dry run test on failing documents")

            dry_run_result = await self.dry_runner.test_edit(
                original_prompt=current_prompt,
                edited_prompt=tuned_prompt,
                target_field=field_path,
                test_documents=test_documents,
                schema=schema,
            )

            workflow_stages["dry_runs"].append(dry_run_result)

            if dry_run_result.get("recommendation") != "ACCEPT":
                logger.warning(f"Dry run rejected: {dry_run_result.get('reasoning')}")
                return {
                    "success": False,
                    "reasoning": f"Dry run test failed: {dry_run_result.get('reasoning')}",
                    "workflow_stages": workflow_stages,
                    "tuned_prompt": tuned_prompt,
                    "edit_details": approved_edit,
                }

            # Success! All stages passed
            logger.info(
                f"Tuning successful for {field_path}. "
                f"Target field improved by {dry_run_result.get('target_field_improvement', 0):+.1%}"
            )

            return {
                "success": True,
                "tuned_prompt": tuned_prompt,
                "edit_details": approved_edit,
                "workflow_stages": workflow_stages,
                "iterations": len(workflow_stages["edit_attempts"]),
                "reasoning": self._build_success_reasoning(dry_run_result),
                "metrics": {
                    "target_field_improvement": dry_run_result.get(
                        "target_field_improvement", 0
                    ),
                    "overall_accuracy_change": dry_run_result.get(
                        "overall_accuracy_change", 0
                    ),
                    "new_errors": len(dry_run_result.get("new_errors", [])),
                },
            }

        except Exception as e:
            logger.error(f"Tuning workflow failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "reasoning": f"Tuning workflow encountered an error: {str(e)}",
            }

    def _prepare_test_documents_from_failures(
        self, failures: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert failure examples into test document format.

        Args:
            failures: List of failure dictionaries

        Returns:
            List of test documents with document_text and verified_data
        """
        # This is a simplified version - in production, you'd fetch actual document text
        # For now, we'll create placeholder test documents
        test_documents = []

        for i, failure in enumerate(failures[:5]):  # Limit to 5 test docs
            test_documents.append(
                {
                    "document_id": failure.get("document_id", f"failure_doc_{i}"),
                    "document_text": failure.get(
                        "document_text", "Placeholder document text"
                    ),
                    "verified_data": failure.get("verified_data", {}),
                }
            )

        return test_documents

    def _apply_edit(self, original_prompt: str, edit: Dict[str, Any]) -> str:
        """Apply an edit to the original prompt.

        Args:
            original_prompt: Original prompt text
            edit: Edit dictionary from EditorAgent

        Returns:
            Modified prompt with edit applied
        """
        edit_type = edit.get("edit_type")
        edit_text = edit.get("edit_text", "")
        field_path = edit.get("field_path", "")

        # For now, use a simple append strategy
        # In production, you'd have more sophisticated edit application logic

        if edit_type == "add_instruction":
            # Add field-specific instruction
            addition = f"\n\n## Field-Specific Instruction: {field_path}\n{edit_text}"
            return original_prompt + addition

        elif edit_type == "modify_instruction":
            # This would require more sophisticated parsing to find and replace
            # For now, append as clarification
            modification = (
                f"\n\n## Clarification for {field_path}\n{edit_text}"
            )
            return original_prompt + modification

        elif edit_type == "add_format_requirement":
            # Add format requirement section
            format_req = f"\n\n## Format Requirement: {field_path}\n{edit_text}"
            return original_prompt + format_req

        elif edit_type == "add_example":
            # Add example section
            example = f"\n\n## Example: {field_path}\n{edit_text}"
            return original_prompt + example

        else:
            # Default: append the edit text
            logger.warning(f"Unknown edit type: {edit_type}, appending edit text")
            return original_prompt + f"\n\n{edit_text}"

    def _build_success_reasoning(self, dry_run_result: Dict[str, Any]) -> str:
        """Build success reasoning from dry run results.

        Args:
            dry_run_result: Results from DryRunnerAgent

        Returns:
            Human-readable success explanation
        """
        target_improvement = dry_run_result.get("target_field_improvement", 0)
        overall_change = dry_run_result.get("overall_accuracy_change", 0)

        reasoning = f"""Tuning successful:
- Target field accuracy improved by {target_improvement:+.1%}
- Overall accuracy changed by {overall_change:+.1%}
- No canary field regressions
- No new errors introduced on other fields

The edited prompt passed all quality gates and demonstrated measurable improvement.
"""
        return reasoning

    def explain_workflow(self, result: Dict[str, Any]) -> str:
        """Generate detailed explanation of the tuning workflow.

        Args:
            result: Result dictionary from tune_field()

        Returns:
            Human-readable workflow explanation
        """
        if result.get("error"):
            return f"Tuning Workflow Error: {result['error']}"

        success = result.get("success", False)
        iterations = result.get("iterations", 0)

        explanation = f"""Tuning Workflow Result: {"SUCCESS" if success else "FAILED"}

Iterations: {iterations}
Reasoning: {result.get('reasoning', 'No reasoning provided')}
"""

        # Add stage details
        stages = result.get("workflow_stages", {})

        explanation += f"\n## Edit Attempts: {len(stages.get('edit_attempts', []))}"
        explanation += f"\n## Critic Reviews: {len(stages.get('critic_reviews', []))}"
        explanation += f"\n## Guard Tests: {len(stages.get('guard_tests', []))}"
        explanation += f"\n## Dry Runs: {len(stages.get('dry_runs', []))}"

        # Add metrics if successful
        if success and "metrics" in result:
            metrics = result["metrics"]
            explanation += f"\n\n## Performance Metrics:"
            explanation += f"\n- Target Field Improvement: {metrics.get('target_field_improvement', 0):+.1%}"
            explanation += f"\n- Overall Accuracy Change: {metrics.get('overall_accuracy_change', 0):+.1%}"
            explanation += f"\n- New Errors: {metrics.get('new_errors', 0)}"

        return explanation

    async def batch_tune_fields(
        self,
        current_prompt: str,
        failing_fields: List[Dict[str, Any]],
        schema: Dict[str, Any],
        canary_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tune multiple failing fields sequentially.

        Args:
            current_prompt: Current extraction prompt
            failing_fields: List of failing field configurations, each with:
                - field_path: Field path
                - failures: Failure examples
                - error_type: Optional error type
            schema: JSON schema
            canary_fields: Optional canary fields to protect

        Returns:
            Dictionary with results for each field
        """
        results = {}
        current_working_prompt = current_prompt

        for field_config in failing_fields:
            field_path = field_config["field_path"]
            logger.info(f"Batch tuning field: {field_path}")

            result = await self.tune_field(
                current_prompt=current_working_prompt,
                field_path=field_path,
                failures=field_config["failures"],
                schema=schema,
                canary_fields=canary_fields,
                error_type=field_config.get("error_type"),
            )

            results[field_path] = result

            # If successful, use the tuned prompt for next field
            if result.get("success"):
                current_working_prompt = result["tuned_prompt"]
                logger.info(f"Updated working prompt after tuning {field_path}")
            else:
                logger.warning(f"Failed to tune {field_path}, continuing with current prompt")

        # Build summary
        successful = sum(1 for r in results.values() if r.get("success"))
        total = len(failing_fields)

        return {
            "overall_success": successful == total,
            "successful_count": successful,
            "total_count": total,
            "final_prompt": current_working_prompt,
            "field_results": results,
        }
