class UnstractWorker:
    BASE_API_ENDPOINT = "/v1/api"
    RUN_API_ENDPOINT = "/container/run"
    SPEC_API_ENDPOINT = "/container/spec"
    PROPERTIES_API_ENDPOINT = "/container/properties"
    ICON_API_ENDPOINT = "/container/icon"
    VARIABLES_API_ENDPOINT = "/container/variables"


class ToolCommandKey:
    PROPERTIES = "properties"
    SPEC = "spec"
    VARIABLES = "variables"
    ICON = "icon"
