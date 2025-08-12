import functools
import logging
import time
import uuid

from requests import Response
from requests.exceptions import RequestException

from unstract.sdk1.constants import Common, LogLevel, MimeType
from unstract.sdk1.utils.metrics_mixin import MetricsMixin

logger = logging.getLogger(__name__)


class Utils:
    @staticmethod
    def generate_uuid() -> str:
        """Class method to get uuid."""
        return str(uuid.uuid4())

    @staticmethod
    def str_to_bool(string: str) -> bool:
        """String value of boolean to boolean.

        Useful while parsing envs to bool.

        Args:
            string (str): value like "true", "True" etc..

        Returns:
            bool
        """
        return string.lower() == "true"

    @staticmethod
    def pretty_file_size(num: float, suffix: str = "B") -> str:
        """Gets the human readable size for a file,

        Args:
            num (int): Size in bytes to parse
            suffix (str, optional): _description_. Defaults to "B".

        Returns:
            str: Human readable size
        """
        for unit in ("", "K", "M", "G", "T"):
            if abs(num) < 1024.0:
                return f"{num:.2f} {unit}{suffix}"
            num /= 1024.0
        return f"{num:.2f} {suffix}"

    @staticmethod
    def get_msg_from_request_exc(
        err: RequestException,
        message_key: str,
        default_err: str = Common.DEFAULT_ERR_MESSAGE,
    ) -> str:
        """Gets the message from the RequestException.

        Args:
            err_response (Response): Error response from the exception
            message_key (str): Key from response containing error message

        Returns:
            str: Error message returned by the server
        """
        if not hasattr(err, "response"):
            return default_err

        err_response: Response = err.response  # type: ignore
        err_content_type = err_response.headers.get("Content-Type")

        if not err_content_type:
            logger.warning(
                f"Content-Type header not found in {err_response}, "
                f"returning {default_err}"
            )
            return default_err

        if err_content_type == MimeType.JSON:
            err_json = err_response.json()
            if message_key in err_json:
                return str(err_json[message_key])
            else:
                logger.warning(
                    f"Unable to parse error with key '{message_key}' for "
                    f"'{err_json}', returning '{default_err}' instead."
                )
        elif err_content_type == MimeType.TEXT:
            return err_response.text  # type: ignore
        else:
            logger.warning(
                f"Unhandled err_response type '{err_content_type}' "
                f"for {err_response}, returning {default_err}"
            )
        return default_err

class TokenCounterCompat:

    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        self.prompt_llm_token_count = prompt_tokens
        self.completion_llm_token_count = completion_tokens
        self.total_llm_token_count = total_tokens
        self.total_embedding_token_count = 0

class LLMResponseCompat:
    def __init__(self, text):
        self.text = text

# Mapping from python log level to Unstract counterpart
PY_TO_UNSTRACT_LOG_LEVEL = {
    logging.DEBUG: LogLevel.DEBUG,
    logging.INFO: LogLevel.INFO,
    logging.WARNING: LogLevel.WARN,
    logging.ERROR: LogLevel.ERROR,
}


def log_elapsed(operation):
    """Adds an elapsed time log.

    Args:
        operation (str): Operation being measured
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
            finally:
                end_time = time.time()
                elapsed_time = end_time - start_time
                logger.info(f"Time taken for '{operation}': {elapsed_time:.3f}s")
            return result

        return wrapper

    return decorator


def capture_metrics(func):
    """Decorator to capture metrics at the start and end of a function."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Ensure the required attributes exist; if not,
        # execute the function and return its result
        if not all(
            hasattr(self, attr) for attr in ["_run_id", "_capture_metrics", "_metrics"]
        ):
            return func(self, *args, **kwargs)

        # Check if run_id exists and if metrics should be captured
        metrics_mixin = None
        time_taken_key = MetricsMixin.TIME_TAKEN_KEY
        if self._run_id and self._capture_metrics:
            metrics_mixin = MetricsMixin(run_id=self._run_id)

        try:
            result = func(self, *args, **kwargs)
        finally:
            # If metrics are being captured, collect and assign them at the end
            if metrics_mixin:
                new_metrics = metrics_mixin.collect_metrics()

                # If time_taken(s) exists in both self._metrics and new_metrics, sum it
                if (
                    self._metrics
                    and time_taken_key in self._metrics
                    and time_taken_key in new_metrics
                ):
                    previously_measured_time = self._metrics.get(time_taken_key)
                    newly_measured_time = new_metrics.get(time_taken_key)

                    # Only sum if both are valid
                    if previously_measured_time and newly_measured_time:
                        self._metrics[time_taken_key] = (
                            previously_measured_time + newly_measured_time
                        )
                    else:
                        self._metrics[time_taken_key] = None
                else:
                    # If the key isn't in self._metrics, set it to new_metrics
                    self._metrics = new_metrics

        return result

    return wrapper
