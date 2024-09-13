from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Union
from urllib.parse import urlencode, urljoin

from api_v2.constants import ApiExecution
from api_v2.models import APIDeployment
from api_v2.postman_collection.constants import CollectionKey
from django.conf import settings
from pipeline_v2.models import Pipeline
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


class APIBase(ABC):

    # @abstractmethod
    # def get_name(self) -> str:
    #     pass

    # @abstractmethod
    # def get_description(self) -> str:
    #     pass

    @abstractmethod
    def get_form_data_items(self) -> list[FormDataItem]:
        pass

    @abstractmethod
    def get_api_endpoint(self) -> str:
        pass

    @abstractmethod
    def get_postman_items(self) -> list[PostmanItem]:
        pass

    @abstractmethod
    def get_api_key(self) -> str:
        pass

    def get_execute_body(self) -> BodyItem:
        form_data_items = self.get_form_data_items()
        return BodyItem(formdata=form_data_items)

    def get_create_api_request(self) -> RequestItem:
        header_list = [
            HeaderItem(key="Authorization", value=f"Bearer {self.get_api_key()}")
        ]
        abs_api_endpoint = urljoin(settings.WEB_APP_ORIGIN_URL, self.get_api_endpoint())
        return RequestItem(
            method=HTTPMethod.POST,
            header=header_list,
            body=self.get_execute_body(),
            url=abs_api_endpoint,
        )


@dataclass
class APIDeploymentDto(APIBase):
    display_name: str
    description: str
    api_endpoint: str
    api_key: str

    def get_postman_info(self) -> PostmanInfo:
        return PostmanInfo(name=self.display_name, description=self.description)

    def get_form_data_items(self) -> list[FormDataItem]:
        return [
            FormDataItem(
                key=ApiExecution.FILES_FORM_DATA, type="file", src="/path_to_file"
            ),
            FormDataItem(
                key=ApiExecution.TIMEOUT_FORM_DATA,
                type="text",
                value=ApiExecution.MAXIMUM_TIMEOUT_IN_SEC,
            ),
            FormDataItem(key=ApiExecution.INCLUDE_METADATA, type="text", value="False"),
        ]

    def get_api_key(self) -> str:
        return self.api_key

    def get_api_endpoint(self) -> str:
        return self.api_endpoint

    def _get_status_api_request(self) -> RequestItem:
        header_list = [HeaderItem(key="Authorization", value=f"Bearer {self.api_key}")]
        status_query_param = {
            "execution_id": CollectionKey.STATUS_EXEC_ID_DEFAULT,
            ApiExecution.INCLUDE_METADATA: "False",
        }
        status_query_str = urlencode(status_query_param)
        abs_api_endpoint = urljoin(settings.WEB_APP_ORIGIN_URL, self.api_endpoint)
        status_url = urljoin(abs_api_endpoint, "?" + status_query_str)
        return RequestItem(method=HTTPMethod.GET, header=header_list, url=status_url)

    def get_postman_items(self) -> list[PostmanItem]:
        postman_item_list = [
            PostmanItem(
                name=CollectionKey.EXECUTE_API_KEY,
                request=self.get_create_api_request(),
            ),
            PostmanItem(
                name=CollectionKey.STATUS_API_KEY,
                request=self._get_status_api_request(),
            ),
        ]
        return postman_item_list


@dataclass
class PipelineDto(APIBase):
    pipeline_name: str
    api_endpoint: str
    api_key: str

    def get_postman_info(self) -> PostmanInfo:
        return PostmanInfo(name=self.pipeline_name, description="")

    def get_form_data_items(self) -> list[FormDataItem]:
        return []

    def get_api_endpoint(self) -> str:
        return self.api_endpoint

    def get_api_key(self) -> str:
        return self.api_key

    def get_postman_items(self) -> list[PostmanItem]:
        postman_item_list = [
            PostmanItem(
                name=CollectionKey.EXECUTE_PIPELINE_API_KEY,
                request=self.get_create_api_request(),
            )
        ]
        return postman_item_list


@dataclass
class PostmanCollection:
    info: PostmanInfo
    item: list[PostmanItem] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        instance: Union[APIDeployment, Pipeline],
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
        data_object: APIBase
        if isinstance(instance, APIDeployment):
            data_object = APIDeploymentDto(
                display_name=instance.display_name,
                description=instance.description,
                api_endpoint=instance.api_endpoint,
                api_key=api_key,
            )
        elif isinstance(instance, Pipeline):
            data_object = PipelineDto(
                pipeline_name=instance.pipeline_name,
                api_endpoint=instance.api_endpoint,
                api_key=api_key,
            )
        postman_info: PostmanInfo = data_object.get_postman_info()
        postman_item_list = data_object.get_postman_items()
        return cls(info=postman_info, item=postman_item_list)

    def to_dict(self) -> dict[str, Any]:
        """Convert PostmanCollection instance to a dict.

        Returns:
            dict[str, Any]: PostmanCollection as a dict
        """
        collection_dict = asdict(self)
        return collection_dict
