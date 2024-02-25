class SchedulerConstants:
    """Constants used by the scheduler app."""

    # Adding a cron job
    ID = "id"
    NAME = "name"
    JOB_KWARGS = "job_kwargs"
    SCHEDULER_KWARGS = "scheduler_kwargs"

    # Default strings
    DEFAULT_CRON_STRING = "0 9 * * 1"
    JOB_ID_REPLACE_TAG = "<job_id>"
