from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode, urljoin

from api_v2.constants import ApiExecution
from api_v2.models import APIDeployment
from api_v2.postman_collection.constants import CollectionKey
from django.conf import settings
from utils.request import HTTPMethod


@dataclass
class HeaderItem:
    key: str
    value: str


@dataclass
class FormDataItem:
    key: str
    type: str
    src: Optional[str] = None
    value: Optional[str] = None

    def __post_init__(self) -> None:
        if self.type == "file":
            if self.src is None:
                raise ValueError("src must be provided for type 'file'")
        elif self.type == "text":
            if self.value is None:
                raise ValueError("value must be provided for type 'text'")
        else:
            raise ValueError(f"Unsupported type for form data: {self.type}")


@dataclass
class BodyItem:
    formdata: list[FormDataItem]
    mode: str = "formdata"


@dataclass
class RequestItem:
    method: HTTPMethod
    url: str
    header: list[HeaderItem]
    body: Optional[BodyItem] = None


@dataclass
class PostmanItem:
    name: str
    request: RequestItem


@dataclass
class PostmanInfo:
    name: str = "Unstract's API deployment"
    schema: str = CollectionKey.POSTMAN_COLLECTION_V210
    description: str = "Contains APIs meant for using the deployed Unstract API"


@dataclass
class PostmanCollection:
    info: PostmanInfo
    item: list[PostmanItem] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        instance: APIDeployment,
        api_key: str = CollectionKey.AUTH_QUERY_PARAM_DEFAULT,
    ) -> "PostmanCollection":
        """Creates a PostmanCollection instance.

        This instance can help represent Postman collections (v2 format) that
        can be used to easily invoke workflows deployed as APIs

        Args:
            instance (APIDeployment): API deployment to generate collection for
            api_key (str, optional): Active API key used to authenticate requests for
                deployed APIs. Defaults to CollectionKey.AUTH_QUERY_PARAM_DEFAULT.

        Returns:
            PostmanCollection: Instance representing PostmanCollection
        """
        postman_info = PostmanInfo(
            name=instance.display_name, description=instance.description
        )
        header_list = [HeaderItem(key="Authorization", value=f"Bearer {api_key}")]
        abs_api_endpoint = urljoin(settings.WEB_APP_ORIGIN_URL, instance.api_endpoint)

        # API execution API
        execute_body = BodyItem(
            formdata=[
                FormDataItem(
                    key=ApiExecution.FILES_FORM_DATA, type="file", src="/path_to_file"
                ),
                FormDataItem(
                    key=ApiExecution.TIMEOUT_FORM_DATA,
                    type="text",
                    value=ApiExecution.MAXIMUM_TIMEOUT_IN_SEC,
                ),
                FormDataItem(
                    key=ApiExecution.INCLUDE_METADATA,
                    type="text",
                    value=False,
                ),
            ]
        )
        execute_request = RequestItem(
            method=HTTPMethod.POST,
            header=header_list,
            body=execute_body,
            url=abs_api_endpoint,
        )

        # Status API
        status_query_param = {"execution_id": CollectionKey.STATUS_EXEC_ID_DEFAULT}
        status_query_str = urlencode(status_query_param)
        status_url = urljoin(abs_api_endpoint, "?" + status_query_str)
        status_request = RequestItem(
            method=HTTPMethod.GET, header=header_list, url=status_url
        )

        postman_item_list = [
            PostmanItem(name=CollectionKey.EXECUTE_API_KEY, request=execute_request),
            PostmanItem(name=CollectionKey.STATUS_API_KEY, request=status_request),
        ]
        return cls(info=postman_info, item=postman_item_list)

    def to_dict(self) -> dict[str, Any]:
        """Convert PostmanCollection instance to a dict.

        Returns:
            dict[str, Any]: PostmanCollection as a dict
        """
        collection_dict = asdict(self)
        return collection_dict
