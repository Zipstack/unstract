import logging
from collections.abc import Callable

import tiktoken
from llama_index.core.callbacks import CallbackManager as LlamaIndexCallbackManager
from llama_index.core.callbacks import TokenCountingHandler
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM
from unstract.sdk1.usage_handler import UsageHandler

logger = logging.getLogger(__name__)


class CallbackManager:
    """Class representing the CallbackManager to manage callbacks.

    Use this over the default service context of llama index

    This class supports a tokenizer, token counter,
    usage handler, and  callback manager.
    """

    @staticmethod
    def set_callback(
        platform_api_key: str,
        model: LLM | BaseEmbedding,
        kwargs,
    ) -> None:
        """Sets the standard callback manager for LlamaIndex embedding. This is
        to be called explicitly to set the handlers which are invoked in the
        callback handling.

        Parameters:
            platform_api_key (str)  : Platform API key
            model (BaseEmbedding)   : LlamaIndex embedding model

        Returns:
            None

        Example:
            set_callback(
                platform_api_key="abc",
                model=embedding,
                **kwargs
            )
        """
        # Nothing to do if callback manager is already set for the instance
        if model and model.callback_manager and len(model.callback_manager.handlers) > 0:
            return

        model.callback_manager = CallbackManager.get_callback_manager(
            model, platform_api_key, kwargs
        )

    @staticmethod
    def get_callback_manager(
        model: LLM | BaseEmbedding,
        platform_api_key: str,
        kwargs,
    ) -> LlamaIndexCallbackManager:
        embedding = None
        handler_list = []
        if isinstance(model, BaseEmbedding):
            embedding = model
            # Get a tokenizer
            tokenizer = CallbackManager.get_tokenizer(model)
            token_counter = TokenCountingHandler(tokenizer=tokenizer, verbose=True)
            usage_handler = UsageHandler(
                token_counter=token_counter,
                platform_api_key=platform_api_key,
                embed_model=embedding,
                kwargs=kwargs,
            )
            handler_list.append(token_counter)
            handler_list.append(usage_handler)

        callback_manager: LlamaIndexCallbackManager = LlamaIndexCallbackManager(
            handlers=handler_list
        )
        return callback_manager

    @staticmethod
    def get_tokenizer(
        model: BaseEmbedding | None,
        fallback_tokenizer: Callable[[str], list] = tiktoken.encoding_for_model(
            "gpt-3.5-turbo"
        ).encode,
    ) -> Callable[[str], list]:
        """Returns a tokenizer function based on the provided model.

        Args:
            model (Optional[Union[LLM, BaseEmbedding]]): The model to use for
            tokenization.

        Returns:
            Callable[[str], List]: The tokenizer function.

        Raises:
            OSError: If an error occurs while loading the tokenizer.
        """
        try:
            if isinstance(model, BaseEmbedding):
                model_name = model.model_name

            tokenizer: Callable[[str], list] = tiktoken.encoding_for_model(
                model_name
            ).encode
            return tokenizer
        except (KeyError, ValueError) as e:
            logger.warning(str(e))
            return fallback_tokenizer
