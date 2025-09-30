from unstract.core.pubsub_helper import LogPublisher
from unstract.flags.feature_flag import check_feature_flag_status
from unstract.prompt_service.constants import RunLevel

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import LogLevel
else:
    from unstract.sdk.constants import LogLevel


def publish_log(
    log_events_id: str,
    component: dict[str, str],
    level: LogLevel,
    state: RunLevel,
    message: str,
) -> None:
    """Publishes a log to the web socket.

    Args:
        log_events_id (str): UUID for the connection
        component (dict[str, str]): Dict of tool_id, doc_name and prompt_name to
            log context
        level (LogLevel): Log level, one of INFO, WARNING, DEBUG, ERROR
        state (RunLevel): Run level, one of EVAL, RUN, CHALLENGE, TABLE_EXTRACTION
        message (str): Message to log
    """
    LogPublisher.publish(
        log_events_id,
        LogPublisher.log_prompt(component, level.value, state.value, message),
    )
