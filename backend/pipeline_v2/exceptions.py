from rest_framework.exceptions import APIException


class NotFoundException(APIException):
    status_code = 404
    default_detail = "The requested resource was not found."


class WorkflowTriggerError(APIException):
    status_code = 400
    default_detail = "Error triggering workflow. Pipeline created"


class PipelineExecuteError(APIException):
    status_code = 500
    default_detail = "Error executing pipline"


class InactivePipelineError(APIException):
    status_code = 422
    default_detail = "Pipeline is inactive, please activate the pipeline"

    def __init__(
        self,
        pipeline_name: str | None = None,
        detail: str | None = None,
        code: str | None = None,
    ):
        if pipeline_name:
            self.default_detail = (
                f"Pipeline '{pipeline_name}' is inactive, please activate the pipeline"
            )
        super().__init__(detail, code)


class MandatoryPipelineType(APIException):
    status_code = 400
    default_detail = "Pipeline type is mandatory"


class MandatoryWorkflowId(APIException):
    status_code = 400
    default_detail = "Workflow ID is mandatory"


class MandatoryCronSchedule(APIException):
    status_code = 400
    default_detail = "Cron schedule is mandatory"


class PipelineNotFound(NotFoundException):
    default_detail = "Pipeline not found"
