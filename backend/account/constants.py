class OAuthConstant:
    TOKEN_USER_INFO_FEILD = "userinfo"
    TOKEN_ORG_ID_FEILD = "org_id"
    TOKEN_EMAIL_FEILD = "email"
    TOKEN_Z_ID_FEILD = "sub"
    TOKEN_USER_NAME_FEILD = "name"
    TOKEN_PRIMARY_Z_ID_FEILD = "primary_sub"


class LoginConstant:
    INVITATION = "invitation"
    ORGANIZATION = "organization"
    ORGANIZATION_NAME = "organization_name"


class Common:
    NEXT_URL_VARIABLE = "next"
    PUBLIC_SCHEMA_NAME = "public"
    ID = "id"
    USER_ID = "user_id"
    USER_EMAIL = "email"
    USER_EMAILS = "emails"
    USER_IDS = "user_ids"
    USER_ROLE = "role"
    MAX_EMAIL_IN_REQUEST = 10


class UserModel:
    USER_ID = "user_id"
    ID = "id"


class OrganizationMemberModel:
    USER_ID = "user__user_id"
    ID = "user__id"


class Cookie:
    ORG_ID = "org_id"
    Z_CODE = "z_code"
    CSRFTOKEN = "csrftoken"
    APP_ID = "app_id"


class ErrorMessage:
    ORGANIZATION_EXIST = "Organization already exists"
    DUPLICATE_API = "It appears that a duplicate call may have been made."


class DefaultOrg:
    ORGANIZATION_NAME = "mock_org"
    MOCK_ORG = "mock_org"
    MOCK_USER = "mock_user"
    MOCK_USER_ID = "mock_user_id"
    MOCK_USER_EMAIL = "email@mock.com"


class PluginConfig:
    PLUGINS_APP = "plugins"
    AUTH_MODULE_PREFIX = "auth"
    AUTH_PLUGIN_DIR = "authentication"
    AUTH_MODULE = "module"
    AUTH_METADATA = "metadata"
    METADATA_SERVICE_CLASS = "service_class"
    METADATA_IS_ACTIVE = "is_active"


class AuthoErrorCode:
    """Error code reference
    frontend/src/components/error/GenericError/GenericError.jsx."""

    IDM = "IDM"
    UMM = "UMM"
    INF = "INF"
    USF = "USF"
