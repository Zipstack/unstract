from rest_framework.exceptions import APIException


class PipelineSaveError(APIException):
    status_code = 500
    default_detail = "Error saving pipeline"


class WorkflowTriggerError(APIException):
    status_code = 400
    default_detail = "Error triggering workflow. Pipeline created"


class PipelineExecuteError(APIException):
    status_code = 500
    default_detail = "Error executing pipline"


class InactivePipelineError(APIException):
    status_code = 422
    default_detail = "Pipeline is inactive, please activate the pipeline"


class MandatoryPipelineType(APIException):
    status_code = 400
    default_detail = "Pipeline type is mandatory"


class MandatoryWorkflowId(APIException):
    status_code = 400
    default_detail = "Workflow ID is mandatory"


class MandatoryCronSchedule(APIException):
    status_code = 400
    default_detail = "Cron schedule is mandatory"


class PipelineDoesNotExistError(APIException):
    status_code = 404
    default_detail = "Pipeline does not exist"
