"""Legacy executor — migrates the prompt-service pipeline.

Phase 2A scaffolds the class with operation routing.
Phase 2B implements ``_handle_extract`` (text extraction via x2text).
Phase 2C implements ``_handle_index`` (vector DB indexing).
Remaining handler methods raise ``NotImplementedError`` and are filled
in by phases 2D–2H.
"""

import logging
from pathlib import Path
from typing import Any

from executor.executor_tool_shim import ExecutorToolShim
from executor.executors.constants import ExecutionSource, IndexingConstants as IKeys
from executor.executors.dto import (
    ChunkingConfig,
    FileInfo,
    InstanceIdentifiers,
    ProcessingOptions,
)
from executor.executors.exceptions import ExtractionError, LegacyExecutorError
from executor.executors.file_utils import FileUtils
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.llm_whisperer.src import LLMWhisperer
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult
from unstract.sdk1.utils.tool import ToolUtils
from unstract.sdk1.x2txt import TextExtractionResult, X2Text

logger = logging.getLogger(__name__)


@ExecutorRegistry.register
class LegacyExecutor(BaseExecutor):
    """Executor that wraps the full prompt-service extraction pipeline.

    Routes incoming ``ExecutionContext`` requests to the appropriate
    handler method based on the ``Operation`` enum.  Each handler
    corresponds to one of the original prompt-service HTTP endpoints.
    """

    # Maps Operation enum values to handler method names.
    _OPERATION_MAP: dict[str, str] = {
        Operation.EXTRACT.value: "_handle_extract",
        Operation.INDEX.value: "_handle_index",
        Operation.ANSWER_PROMPT.value: "_handle_answer_prompt",
        Operation.SINGLE_PASS_EXTRACTION.value: "_handle_single_pass_extraction",
        Operation.SUMMARIZE.value: "_handle_summarize",
        Operation.AGENTIC_EXTRACTION.value: "_handle_agentic_extraction",
    }

    @property
    def name(self) -> str:
        return "legacy"

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Route to the handler for ``context.operation``.

        Returns:
            ``ExecutionResult`` on success or for unsupported operations.
            ``LegacyExecutorError`` subclasses are caught and mapped to
            ``ExecutionResult.failure()`` so callers always get a result.

        Raises:
            NotImplementedError: From stub handlers (until 2D–2H).
        """
        handler_name = self._OPERATION_MAP.get(context.operation)
        if handler_name is None:
            return ExecutionResult.failure(
                error=(
                    f"LegacyExecutor does not support operation "
                    f"'{context.operation}'"
                )
            )

        handler = getattr(self, handler_name)
        logger.info(
            "LegacyExecutor routing operation=%s to %s "
            "(run_id=%s request_id=%s)",
            context.operation,
            handler_name,
            context.run_id,
            context.request_id,
        )
        try:
            return handler(context)
        except LegacyExecutorError as exc:
            logger.warning(
                "Handler %s raised %s: %s",
                handler_name,
                type(exc).__name__,
                exc.message,
            )
            return ExecutionResult.failure(error=exc.message)

    # ------------------------------------------------------------------
    # Phase 2B — Extract handler
    # ------------------------------------------------------------------

    def _handle_extract(self, context: ExecutionContext) -> ExecutionResult:
        """Handle ``Operation.EXTRACT`` — text extraction via x2text.

        Migrated from ``ExtractionService.perform_extraction()`` in
        ``prompt-service/.../services/extraction.py``.

        Returns:
            ExecutionResult with ``data`` containing ``extracted_text``.
        """
        params: dict[str, Any] = context.executor_params

        # Required params
        x2text_instance_id: str = params.get(IKeys.X2TEXT_INSTANCE_ID, "")
        file_path: str = params.get(IKeys.FILE_PATH, "")
        platform_api_key: str = params.get("platform_api_key", "")

        if not x2text_instance_id or not file_path:
            missing = []
            if not x2text_instance_id:
                missing.append(IKeys.X2TEXT_INSTANCE_ID)
            if not file_path:
                missing.append(IKeys.FILE_PATH)
            return ExecutionResult.failure(
                error=f"Missing required params: {', '.join(missing)}"
            )

        # Optional params
        output_file_path: str | None = params.get(IKeys.OUTPUT_FILE_PATH)
        enable_highlight: bool = params.get(IKeys.ENABLE_HIGHLIGHT, False)
        usage_kwargs: dict[Any, Any] = params.get(IKeys.USAGE_KWARGS, {})
        tags: list[str] | None = params.get(IKeys.TAGS)
        execution_source: str = context.execution_source
        tool_exec_metadata: dict[str, Any] = params.get(
            IKeys.TOOL_EXECUTION_METATADA, {}
        )
        execution_data_dir: str | None = params.get(IKeys.EXECUTION_DATA_DIR)

        # Build adapter shim and X2Text
        shim = ExecutorToolShim(platform_api_key=platform_api_key)
        x2text = X2Text(
            tool=shim,
            adapter_instance_id=x2text_instance_id,
            usage_kwargs=usage_kwargs,
        )
        fs = FileUtils.get_fs_instance(execution_source=execution_source)

        try:
            if enable_highlight and isinstance(
                x2text.x2text_instance, (LLMWhisperer, LLMWhispererV2)
            ):
                process_response: TextExtractionResult = x2text.process(
                    input_file_path=file_path,
                    output_file_path=output_file_path,
                    enable_highlight=enable_highlight,
                    tags=tags,
                    fs=fs,
                )
                self._update_exec_metadata(
                    fs=fs,
                    execution_source=execution_source,
                    tool_exec_metadata=tool_exec_metadata,
                    execution_data_dir=execution_data_dir,
                    process_response=process_response,
                )
            else:
                process_response = x2text.process(
                    input_file_path=file_path,
                    output_file_path=output_file_path,
                    tags=tags,
                    fs=fs,
                )

            return ExecutionResult(
                success=True,
                data={IKeys.EXTRACTED_TEXT: process_response.extracted_text},
            )
        except AdapterError as e:
            name = x2text.x2text_instance.get_name()
            msg = f"Error from text extractor '{name}'. {e}"
            raise ExtractionError(message=msg) from e

    @staticmethod
    def _update_exec_metadata(
        fs: Any,
        execution_source: str,
        tool_exec_metadata: dict[str, Any] | None,
        execution_data_dir: str | None,
        process_response: TextExtractionResult,
    ) -> None:
        """Write whisper_hash metadata for tool-sourced executions."""
        if execution_source != ExecutionSource.TOOL.value:
            return
        whisper_hash = process_response.extraction_metadata.whisper_hash
        metadata = {X2TextConstants.WHISPER_HASH: whisper_hash}
        if tool_exec_metadata is not None:
            for key, value in metadata.items():
                tool_exec_metadata[key] = value
        metadata_path = str(Path(execution_data_dir) / IKeys.METADATA_FILE)
        ToolUtils.dump_json(
            file_to_dump=metadata_path,
            json_to_dump=metadata,
            fs=fs,
        )

    @staticmethod
    def _get_indexing_deps():
        """Lazy-import heavy indexing dependencies.

        These imports trigger llama_index/qdrant/protobuf loading,
        so they must not happen at module-collection time (tests).
        Wrapped in a method so tests can mock it cleanly.
        """
        from executor.executors.index import Index
        from unstract.sdk1.embedding import EmbeddingCompat
        from unstract.sdk1.vector_db import VectorDB

        return Index, EmbeddingCompat, VectorDB

    # ------------------------------------------------------------------
    # Phase 2C — Index handler
    # ------------------------------------------------------------------

    def _handle_index(self, context: ExecutionContext) -> ExecutionResult:
        """Handle ``Operation.INDEX`` — vector DB indexing.

        Migrated from ``IndexingService.index()`` in
        ``prompt-service/.../services/indexing.py``.

        Returns:
            ExecutionResult with ``data`` containing ``doc_id``.
        """
        params: dict[str, Any] = context.executor_params

        # Required params
        embedding_instance_id: str = params.get(IKeys.EMBEDDING_INSTANCE_ID, "")
        vector_db_instance_id: str = params.get(IKeys.VECTOR_DB_INSTANCE_ID, "")
        x2text_instance_id: str = params.get(IKeys.X2TEXT_INSTANCE_ID, "")
        file_path: str = params.get(IKeys.FILE_PATH, "")
        extracted_text: str = params.get(IKeys.EXTRACTED_TEXT, "")
        platform_api_key: str = params.get("platform_api_key", "")

        missing = []
        if not embedding_instance_id:
            missing.append(IKeys.EMBEDDING_INSTANCE_ID)
        if not vector_db_instance_id:
            missing.append(IKeys.VECTOR_DB_INSTANCE_ID)
        if not x2text_instance_id:
            missing.append(IKeys.X2TEXT_INSTANCE_ID)
        if not file_path:
            missing.append(IKeys.FILE_PATH)
        if missing:
            return ExecutionResult.failure(
                error=f"Missing required params: {', '.join(missing)}"
            )

        # Optional params
        tool_id: str = params.get(IKeys.TOOL_ID, "")
        file_hash: str | None = params.get(IKeys.FILE_HASH)
        chunk_size: int = params.get(IKeys.CHUNK_SIZE, 512)
        chunk_overlap: int = params.get(IKeys.CHUNK_OVERLAP, 128)
        reindex: bool = params.get(IKeys.REINDEX, False)
        enable_highlight: bool = params.get(IKeys.ENABLE_HIGHLIGHT, False)
        enable_word_confidence: bool = params.get(
            IKeys.ENABLE_WORD_CONFIDENCE, False
        )
        usage_kwargs: dict[Any, Any] = params.get(IKeys.USAGE_KWARGS, {})
        tags: list[str] | None = params.get(IKeys.TAGS)
        execution_source: str = context.execution_source

        instance_ids = InstanceIdentifiers(
            embedding_instance_id=embedding_instance_id,
            vector_db_instance_id=vector_db_instance_id,
            x2text_instance_id=x2text_instance_id,
            tool_id=tool_id,
            tags=tags,
            llm_instance_id=None,
        )
        file_info = FileInfo(file_path=file_path, file_hash=file_hash)
        processing_options = ProcessingOptions(
            reindex=reindex,
            enable_highlight=enable_highlight,
            enable_word_confidence=enable_word_confidence,
            usage_kwargs=usage_kwargs,
        )

        shim = ExecutorToolShim(platform_api_key=platform_api_key)
        fs_instance = FileUtils.get_fs_instance(
            execution_source=execution_source
        )

        # Skip indexing when chunk_size is 0 — no vector operations needed.
        # ChunkingConfig raises ValueError for 0, so handle before DTO.
        if chunk_size == 0:
            from unstract.sdk1.utils.indexing import IndexingUtils

            doc_id = IndexingUtils.generate_index_key(
                vector_db=vector_db_instance_id,
                embedding=embedding_instance_id,
                x2text=x2text_instance_id,
                chunk_size=str(chunk_size),
                chunk_overlap=str(chunk_overlap),
                tool=shim,
                file_path=file_path,
                file_hash=file_hash,
                fs=fs_instance,
            )
            logger.info("Skipping indexing for chunk_size=0. Doc ID: %s", doc_id)
            return ExecutionResult(
                success=True, data={IKeys.DOC_ID: doc_id}
            )

        chunking_config = ChunkingConfig(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        Index, EmbeddingCompat, VectorDB = self._get_indexing_deps()

        vector_db = None
        try:
            index = Index(
                tool=shim,
                run_id=context.run_id,
                capture_metrics=True,
                instance_identifiers=instance_ids,
                chunking_config=chunking_config,
                processing_options=processing_options,
            )
            doc_id = index.generate_index_key(
                file_info=file_info, fs=fs_instance
            )

            embedding = EmbeddingCompat(
                adapter_instance_id=embedding_instance_id,
                tool=shim,
                kwargs={**usage_kwargs},
            )
            vector_db = VectorDB(
                tool=shim,
                adapter_instance_id=vector_db_instance_id,
                embedding=embedding,
            )

            doc_id_found = index.is_document_indexed(
                doc_id=doc_id, embedding=embedding, vector_db=vector_db
            )
            index.perform_indexing(
                vector_db=vector_db,
                doc_id=doc_id,
                extracted_text=extracted_text,
                doc_id_found=doc_id_found,
            )
            return ExecutionResult(
                success=True, data={IKeys.DOC_ID: doc_id}
            )
        except Exception as e:
            status_code = getattr(e, "status_code", 500)
            raise LegacyExecutorError(
                message=f"Error while indexing: {e}", code=status_code
            ) from e
        finally:
            if vector_db is not None:
                vector_db.close()

    @staticmethod
    def _get_prompt_deps():
        """Lazy-import heavy dependencies for answer_prompt processing.

        These imports trigger llama_index/protobuf loading so they must
        not happen at module-collection time (tests).
        """
        from executor.executors.answer_prompt import AnswerPromptService
        from executor.executors.index import Index
        from executor.executors.retrieval import RetrievalService
        from executor.executors.variable_replacement import (
            VariableReplacementService,
        )
        from unstract.sdk1.embedding import EmbeddingCompat
        from unstract.sdk1.llm import LLM
        from unstract.sdk1.vector_db import VectorDB

        return (
            AnswerPromptService,
            RetrievalService,
            VariableReplacementService,
            Index,
            LLM,
            EmbeddingCompat,
            VectorDB,
        )

    @staticmethod
    def _sanitize_null_values(
        structured_output: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace 'NA' strings with None in structured output."""
        for k, v in structured_output.items():
            if isinstance(v, str) and v.lower() == "na":
                structured_output[k] = None
            elif isinstance(v, list):
                for i in range(len(v)):
                    if isinstance(v[i], str) and v[i].lower() == "na":
                        v[i] = None
                    elif isinstance(v[i], dict):
                        for k1, v1 in v[i].items():
                            if isinstance(v1, str) and v1.lower() == "na":
                                v[i][k1] = None
            elif isinstance(v, dict):
                for k1, v1 in v.items():
                    if isinstance(v1, str) and v1.lower() == "na":
                        v[k1] = None
        return structured_output

    def _handle_answer_prompt(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Handle ``Operation.ANSWER_PROMPT`` — multi-prompt extraction.

        Migrated from ``prompt_processor()`` in the prompt-service
        ``answer_prompt`` controller.  Processes all prompts in the
        payload: variable replacement, context retrieval, LLM
        completion, and type-specific post-processing.

        Returns:
            ExecutionResult with ``data`` containing::

                {"output": dict, "metadata": dict, "metrics": dict}
        """
        from executor.executors.constants import (
            PromptServiceConstants as PSKeys,
            RetrievalStrategy,
        )

        params: dict[str, Any] = context.executor_params

        # ---- Unpack payload ------------------------------------------------
        tool_settings = params.get(PSKeys.TOOL_SETTINGS, {})
        prompts = params.get(PSKeys.OUTPUTS, [])
        tool_id: str = params.get(PSKeys.TOOL_ID, "")
        run_id: str = context.run_id
        execution_id: str = params.get(PSKeys.EXECUTION_ID, "")
        file_hash = params.get(PSKeys.FILE_HASH)
        file_path = params.get(PSKeys.FILE_PATH)
        doc_name = str(params.get(PSKeys.FILE_NAME, ""))
        log_events_id: str = params.get(PSKeys.LOG_EVENTS_ID, "")
        custom_data: dict[str, Any] = params.get(PSKeys.CUSTOM_DATA, {})
        execution_source = params.get(
            PSKeys.EXECUTION_SOURCE, context.execution_source
        )
        platform_api_key: str = params.get(
            PSKeys.PLATFORM_SERVICE_API_KEY, ""
        )

        structured_output: dict[str, Any] = {}
        metadata: dict[str, Any] = {
            PSKeys.RUN_ID: run_id,
            PSKeys.FILE_NAME: doc_name,
            PSKeys.CONTEXT: {},
            PSKeys.REQUIRED_FIELDS: {},
        }
        metrics: dict[str, Any] = {}
        variable_names: list[str] = []
        context_retrieval_metrics: dict[str, Any] = {}

        # Lazy imports
        (
            AnswerPromptService,
            RetrievalService,
            VariableReplacementService,
            _Index,  # unused — doc_id via IndexingUtils
            LLM,
            EmbeddingCompat,
            VectorDB,
        ) = self._get_prompt_deps()

        # ---- First pass: collect variable names + required fields ----------
        for output in prompts:
            variable_names.append(output[PSKeys.NAME])
            metadata[PSKeys.REQUIRED_FIELDS][output[PSKeys.NAME]] = output.get(
                PSKeys.REQUIRED, None
            )

        # ---- Process each prompt -------------------------------------------
        for output in prompts:
            prompt_name = output[PSKeys.NAME]
            prompt_text = output[PSKeys.PROMPT]
            chunk_size = output[PSKeys.CHUNK_SIZE]

            logger.info("[%s] chunk size: %s", tool_id, chunk_size)

            shim = ExecutorToolShim(platform_api_key=platform_api_key)

            # {{variable}} template replacement
            if VariableReplacementService.is_variables_present(
                prompt_text=prompt_text
            ):
                is_ide = execution_source == "ide"
                prompt_text = (
                    VariableReplacementService.replace_variables_in_prompt(
                        prompt=output,
                        structured_output=structured_output,
                        log_events_id=log_events_id,
                        tool_id=tool_id,
                        prompt_name=prompt_name,
                        doc_name=doc_name,
                        custom_data=custom_data,
                        is_ide=is_ide,
                    )
                )

            logger.info("[%s] Executing prompt: '%s'", tool_id, prompt_name)

            # %variable% replacement
            output[PSKeys.PROMPTX] = AnswerPromptService.extract_variable(
                structured_output, variable_names, output, prompt_text
            )

            # Generate doc_id (standalone util — no Index DTOs needed)
            from unstract.sdk1.utils.indexing import IndexingUtils

            doc_id = IndexingUtils.generate_index_key(
                vector_db=output[PSKeys.VECTOR_DB],
                embedding=output[PSKeys.EMBEDDING],
                x2text=output[PSKeys.X2TEXT_ADAPTER],
                chunk_size=str(output[PSKeys.CHUNK_SIZE]),
                chunk_overlap=str(output[PSKeys.CHUNK_OVERLAP]),
                tool=shim,
                file_hash=file_hash,
                file_path=file_path,
            )

            # Create adapters
            try:
                usage_kwargs = {
                    "run_id": run_id,
                    "execution_id": execution_id,
                }
                llm = LLM(
                    adapter_instance_id=output[PSKeys.LLM],
                    tool=shim,
                    usage_kwargs={
                        **usage_kwargs,
                        PSKeys.LLM_USAGE_REASON: PSKeys.EXTRACTION,
                    },
                    capture_metrics=True,
                )
                embedding = None
                vector_db = None
                if chunk_size > 0:
                    embedding = EmbeddingCompat(
                        adapter_instance_id=output[PSKeys.EMBEDDING],
                        tool=shim,
                        kwargs={**usage_kwargs},
                    )
                    vector_db = VectorDB(
                        tool=shim,
                        adapter_instance_id=output[PSKeys.VECTOR_DB],
                        embedding=embedding,
                    )
            except Exception as e:
                msg = f"Couldn't fetch adapter. {e}"
                logger.error(msg)
                status_code = getattr(e, "status_code", None) or 500
                raise LegacyExecutorError(
                    message=msg, code=status_code
                ) from e

            # TABLE and LINE_ITEM types require plugins not yet available
            if output[PSKeys.TYPE] == PSKeys.TABLE:
                raise LegacyExecutorError(
                    message=(
                        "TABLE extraction requires plugins not yet "
                        "available in the executor worker."
                    )
                )
            if output[PSKeys.TYPE] == PSKeys.LINE_ITEM:
                raise LegacyExecutorError(
                    message=(
                        "LINE_ITEM extraction requires plugins not yet "
                        "available in the executor worker."
                    )
                )

            # ---- Retrieval + Answer ----------------------------------------
            context_list: list[str] = []
            try:
                answer = "NA"
                retrieval_strategy = output.get(PSKeys.RETRIEVAL_STRATEGY)
                valid_strategies = {s.value for s in RetrievalStrategy}

                if retrieval_strategy in valid_strategies:
                    logger.info(
                        "[%s] Performing retrieval for: %s",
                        tool_id,
                        file_path,
                    )
                    if chunk_size == 0:
                        context_list = (
                            RetrievalService.retrieve_complete_context(
                                execution_source=execution_source,
                                file_path=file_path,
                                context_retrieval_metrics=context_retrieval_metrics,
                                prompt_key=prompt_name,
                            )
                        )
                    else:
                        context_list = RetrievalService.run_retrieval(
                            output=output,
                            doc_id=doc_id,
                            llm=llm,
                            vector_db=vector_db,
                            retrieval_type=retrieval_strategy,
                            context_retrieval_metrics=context_retrieval_metrics,
                        )
                    metadata[PSKeys.CONTEXT][prompt_name] = context_list

                    # Run prompt with retrieved context
                    answer = AnswerPromptService.construct_and_run_prompt(
                        tool_settings=tool_settings,
                        output=output,
                        llm=llm,
                        context="\n".join(context_list),
                        prompt=PSKeys.PROMPTX,
                        metadata=metadata,
                        execution_source=execution_source,
                        file_path=file_path,
                    )
                else:
                    logger.info(
                        "Invalid retrieval strategy: %s", retrieval_strategy
                    )

                # ---- Type-specific post-processing -------------------------
                self._apply_type_conversion(
                    output=output,
                    answer=answer,
                    structured_output=structured_output,
                    llm=llm,
                    tool_settings=tool_settings,
                    metadata=metadata,
                    execution_source=execution_source,
                    file_path=file_path,
                    log_events_id=log_events_id,
                    tool_id=tool_id,
                    doc_name=doc_name,
                )

                # Strip trailing newline
                val = structured_output.get(prompt_name)
                if isinstance(val, str):
                    structured_output[prompt_name] = val.rstrip("\n")

            finally:
                # Collect metrics
                metrics.setdefault(prompt_name, {}).update(
                    {
                        "context_retrieval": context_retrieval_metrics.get(
                            prompt_name, {}
                        ),
                        f"{llm.get_usage_reason()}_llm": llm.get_metrics(),
                    }
                )
                if vector_db:
                    vector_db.close()

        # ---- Sanitize null values ------------------------------------------
        structured_output = self._sanitize_null_values(structured_output)

        return ExecutionResult(
            success=True,
            data={
                PSKeys.OUTPUT: structured_output,
                PSKeys.METADATA: metadata,
                PSKeys.METRICS: metrics,
            },
        )

    @staticmethod
    def _apply_type_conversion(
        output: dict[str, Any],
        answer: str,
        structured_output: dict[str, Any],
        llm: Any,
        tool_settings: dict[str, Any],
        metadata: dict[str, Any],
        execution_source: str,
        file_path: str,
        log_events_id: str = "",
        tool_id: str = "",
        doc_name: str = "",
    ) -> None:
        """Apply type-specific conversion to the LLM answer.

        Handles NUMBER, EMAIL, DATE, BOOLEAN, JSON, and TEXT types.
        """
        from executor.executors.answer_prompt import AnswerPromptService
        from executor.executors.constants import PromptServiceConstants as PSKeys

        prompt_name = output[PSKeys.NAME]
        output_type = output[PSKeys.TYPE]

        if output_type == PSKeys.NUMBER:
            if answer.lower() == "na":
                structured_output[prompt_name] = None
            else:
                prompt = (
                    f"Extract the number from the following "
                    f"text:\n{answer}\n\nOutput just the number. "
                    f"If the number is expressed in millions "
                    f"or thousands, expand the number to its numeric value "
                    f"The number should be directly assignable "
                    f"to a numeric variable. "
                    f"It should not have any commas, "
                    f"percentages or other grouping "
                    f"characters. No explanation is required. "
                    f"If you cannot extract the number, output 0."
                )
                answer = AnswerPromptService.run_completion(
                    llm=llm, prompt=prompt
                )
                try:
                    structured_output[prompt_name] = float(answer)
                except Exception:
                    structured_output[prompt_name] = None

        elif output_type == PSKeys.EMAIL:
            if answer.lower() == "na":
                structured_output[prompt_name] = None
            else:
                prompt = (
                    f"Extract the email from the following text:\n{answer}"
                    f"\n\nOutput just the email. "
                    f"The email should be directly assignable to a string "
                    f"variable. No explanation is required. If you cannot "
                    f'extract the email, output "NA".'
                )
                answer = AnswerPromptService.run_completion(
                    llm=llm, prompt=prompt
                )
                structured_output[prompt_name] = answer

        elif output_type == PSKeys.DATE:
            if answer.lower() == "na":
                structured_output[prompt_name] = None
            else:
                prompt = (
                    f"Extract the date from the following text:\n{answer}"
                    f"\n\nOutput just the date. "
                    f"The date should be in ISO date time format. "
                    f"No explanation is required. The date should be "
                    f"directly assignable to a date variable. "
                    f'If you cannot convert the string into a date, '
                    f'output "NA".'
                )
                answer = AnswerPromptService.run_completion(
                    llm=llm, prompt=prompt
                )
                structured_output[prompt_name] = answer

        elif output_type == PSKeys.BOOLEAN:
            if answer.lower() == "na":
                structured_output[prompt_name] = None
            else:
                prompt = (
                    f"Extract yes/no from the following text:\n{answer}\n\n"
                    f"Output in single word. "
                    f"If the context is trying to convey that the answer "
                    f'is true, then return "yes", else return "no".'
                )
                answer = AnswerPromptService.run_completion(
                    llm=llm, prompt=prompt
                )
                structured_output[prompt_name] = answer.lower() == "yes"

        elif output_type == PSKeys.JSON:
            AnswerPromptService.handle_json(
                answer=answer,
                structured_output=structured_output,
                output=output,
                llm=llm,
                enable_highlight=tool_settings.get(
                    PSKeys.ENABLE_HIGHLIGHT, False
                ),
                enable_word_confidence=tool_settings.get(
                    PSKeys.ENABLE_WORD_CONFIDENCE, False
                ),
                execution_source=execution_source,
                metadata=metadata,
                file_path=file_path,
                log_events_id=log_events_id,
                tool_id=tool_id,
                doc_name=doc_name,
            )

        else:
            # TEXT or any other type — store raw answer
            structured_output[prompt_name] = answer

    def _handle_single_pass_extraction(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Handle ``Operation.SINGLE_PASS_EXTRACTION``.

        Functionally identical to ``_handle_answer_prompt``.  The "single
        pass" vs "multi pass" distinction is at the *caller* level (the
        structure tool batches all prompts into one request vs iterating).
        The prompt-service processes both with the same ``prompt_processor``
        handler.

        Returns:
            ExecutionResult with ``data`` containing::

                {"output": dict, "metadata": dict, "metrics": dict}
        """
        logger.info(
            "single_pass_extraction delegating to answer_prompt "
            "(run_id=%s)",
            context.run_id,
        )
        return self._handle_answer_prompt(context)

    def _handle_summarize(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Handle ``Operation.SUMMARIZE`` — document summarization.

        Called by the structure tool when ``summarize_as_source`` is
        enabled.  Takes the full extracted document text and a
        user-provided summarize prompt, runs LLM completion, and
        returns the summarized text.

        Expected ``executor_params`` keys:
            - ``llm_adapter_instance_id`` — LLM adapter to use
            - ``summarize_prompt`` — user's summarize instruction
            - ``context`` — full document text to summarize
            - ``prompt_keys`` — list of field names to focus on
            - ``PLATFORM_SERVICE_API_KEY`` — auth key for adapters

        Returns:
            ExecutionResult with ``data`` containing::

                {"data": str}   # summarized text
        """
        from executor.executors.constants import PromptServiceConstants as PSKeys

        params: dict[str, Any] = context.executor_params

        llm_adapter_id: str = params.get("llm_adapter_instance_id", "")
        summarize_prompt: str = params.get("summarize_prompt", "")
        doc_context: str = params.get(PSKeys.CONTEXT, "")
        prompt_keys: list[str] = params.get("prompt_keys", [])
        platform_api_key: str = params.get(
            PSKeys.PLATFORM_SERVICE_API_KEY, ""
        )

        if not llm_adapter_id:
            return ExecutionResult.failure(
                error="Missing required param: llm_adapter_instance_id"
            )
        if not doc_context:
            return ExecutionResult.failure(
                error="Missing required param: context"
            )

        # Build the summarize prompt
        prompt = f"{summarize_prompt}\n\n"
        if prompt_keys:
            prompt += (
                f"Focus on these fields: {', '.join(prompt_keys)}\n\n"
            )
        prompt += (
            f"Context:\n---------------\n{doc_context}\n"
            f"-----------------\n\nSummary:"
        )

        shim = ExecutorToolShim(platform_api_key=platform_api_key)
        usage_kwargs = {"run_id": context.run_id}

        _, _, _, _, LLM, _, _ = self._get_prompt_deps()

        try:
            llm = LLM(
                adapter_instance_id=llm_adapter_id,
                tool=shim,
                usage_kwargs={**usage_kwargs},
            )
            from executor.executors.answer_prompt import AnswerPromptService

            summary = AnswerPromptService.run_completion(
                llm=llm, prompt=prompt
            )
            return ExecutionResult(
                success=True,
                data={"data": summary},
            )
        except Exception as e:
            status_code = getattr(e, "status_code", None) or 500
            raise LegacyExecutorError(
                message=f"Error during summarization: {e}",
                code=status_code,
            ) from e

    def _handle_agentic_extraction(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Handle ``Operation.AGENTIC_EXTRACTION``.

        Agentic extraction requires the agentic extraction plugin
        (AutoGen-based multi-agent system).  This is not available
        in the executor worker — it will be migrated when plugin
        support is added.

        Returns:
            ExecutionResult.failure indicating the plugin is required.
        """
        raise LegacyExecutorError(
            message=(
                "Agentic extraction requires the agentic extraction "
                "plugin which is not yet available in the executor "
                "worker."
            ),
        )
