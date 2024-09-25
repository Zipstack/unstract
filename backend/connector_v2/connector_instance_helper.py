import logging
from typing import Any, Optional

from account_v2.models import User
from connector_v2.constants import ConnectorInstanceConstant
from connector_v2.models import ConnectorInstance
from connector_v2.unstract_account import UnstractAccount
from django.conf import settings
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from unstract.connectors.filesystems.ucs import UnstractCloudStorage
from unstract.connectors.filesystems.ucs.constants import UCSKey

logger = logging.getLogger(__name__)


class ConnectorInstanceHelper:
    @staticmethod
    def create_default_gcs_connector(workflow: Workflow, user: User) -> None:
        """Method to create default storage connector.

        Args:
            org_id (str)
            workflow (Workflow)
            user (User)
        """
        organization_id = UserContext.get_organization_identifier()
        if not user.project_storage_created:
            logger.info("Creating default storage")
            account = UnstractAccount(organization_id, user.email)
            account.provision_s3_storage()
            account.upload_sample_files()
            user.project_storage_created = True
            user.save()
            logger.info("default storage created successfully.")

        logger.info("Adding connectors to Unstract")
        connector_name = ConnectorInstanceConstant.USER_STORAGE
        gcs_id = UnstractCloudStorage.get_id()
        bucket_name = settings.UNSTRACT_FREE_STORAGE_BUCKET_NAME
        base_path = f"{bucket_name}/{organization_id}/{user.email}"

        connector_metadata = {
            UCSKey.KEY: settings.GOOGLE_STORAGE_ACCESS_KEY_ID,
            UCSKey.SECRET: settings.GOOGLE_STORAGE_SECRET_ACCESS_KEY,
            UCSKey.ENDPOINT_URL: settings.GOOGLE_STORAGE_BASE_URL,
        }
        connector_metadata__input = {
            **connector_metadata,
            UCSKey.PATH: base_path + "/input",
        }
        connector_metadata__output = {
            **connector_metadata,
            UCSKey.PATH: base_path + "/output",
        }
        ConnectorInstance.objects.create(
            connector_name=connector_name,
            workflow=workflow,
            created_by=user,
            connector_id=gcs_id,
            connector_metadata=connector_metadata__input,
            connector_type=ConnectorInstance.ConnectorType.INPUT,
            connector_mode=ConnectorInstance.ConnectorMode.FILE_SYSTEM,
        )
        ConnectorInstance.objects.create(
            connector_name=connector_name,
            workflow=workflow,
            created_by=user,
            connector_id=gcs_id,
            connector_metadata=connector_metadata__output,
            connector_type=ConnectorInstance.ConnectorType.OUTPUT,
            connector_mode=ConnectorInstance.ConnectorMode.FILE_SYSTEM,
        )
        logger.info("Connectors added successfully.")

    @staticmethod
    def get_connector_instances_by_workflow(
        workflow_id: str,
        connector_type: tuple[str, str],
        connector_mode: Optional[tuple[int, str]] = None,
        values: Optional[list[str]] = None,
        connector_name: Optional[str] = None,
    ) -> list[ConnectorInstance]:
        """Method to get connector instances by workflow.

        Args:
            workflow_id (str)
            connector_type (tuple[str, str]): Specifies input/output
            connector_mode (Optional[tuple[int, str]], optional):
                Specifies database/file
            values (Optional[list[str]], optional):  Defaults to None.
            connector_name (Optional[str], optional):  Defaults to None.

        Returns:
            list[ConnectorInstance]
        """
        logger.info(f"Setting connector mode to {connector_mode}")
        filter_params: dict[str, Any] = {
            "workflow": workflow_id,
            "connector_type": connector_type,
        }
        if connector_mode is not None:
            filter_params["connector_mode"] = connector_mode
        if connector_name is not None:
            filter_params["connector_name"] = connector_name

        connector_instances = ConnectorInstance.objects.filter(**filter_params).all()
        logger.debug(f"Retrieved connector instance values {connector_instances}")
        if values is not None:
            filtered_connector_instances = connector_instances.values(*values)
            logger.info(
                f"Returning filtered \
                    connector instance value {filtered_connector_instances}"
            )
            return list(filtered_connector_instances)
        logger.info(f"Returning connector instances {connector_instances}")
        return list(connector_instances)

    @staticmethod
    def get_connector_instance_by_workflow(
        workflow_id: str,
        connector_type: tuple[str, str],
        connector_mode: Optional[tuple[int, str]] = None,
        connector_name: Optional[str] = None,
    ) -> Optional[ConnectorInstance]:
        """Get one connector instance.

            Use this method if the connector instance is unique for \
                filter_params
        Args:
            workflow_id (str): _description_
            connector_type (tuple[str, str]):  Specifies input/output
            connector_mode (Optional[tuple[int, str]], optional).
                Specifies database/filesystem.
            connector_name (Optional[str], optional).

        Returns:
            list[ConnectorInstance]: _description_
        """
        logger.info("Fetching connector instance by workflow")
        filter_params: dict[str, Any] = {
            "workflow": workflow_id,
            "connector_type": connector_type,
        }
        if connector_mode is not None:
            filter_params["connector_mode"] = connector_mode
        if connector_name is not None:
            filter_params["connector_name"] = connector_name

        try:
            connector_instance: ConnectorInstance = ConnectorInstance.objects.filter(
                **filter_params
            ).first()
        except Exception as exc:
            logger.error(f"Error occured while fetching connector instances {exc}")
            raise exc

        return connector_instance

    @staticmethod
    def get_input_connector_instance_by_name_for_workflow(
        workflow_id: str,
        connector_name: str,
    ) -> Optional[ConnectorInstance]:
        """Method to get Input connector instance name from the workflow.

        Args:
            workflow_id (str)
            connector_name (str)

        Returns:
            Optional[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instance_by_workflow(
            workflow_id=workflow_id,
            connector_type=ConnectorInstance.ConnectorType.INPUT,
            connector_name=connector_name,
        )

    @staticmethod
    def get_output_connector_instance_by_name_for_workflow(
        workflow_id: str,
        connector_name: str,
    ) -> Optional[ConnectorInstance]:
        """Method to get output connector name by Workflow.

        Args:
            workflow_id (str)
            connector_name (str)

        Returns:
            Optional[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instance_by_workflow(
            workflow_id=workflow_id,
            connector_type=ConnectorInstance.ConnectorType.OUTPUT,
            connector_name=connector_name,
        )

    @staticmethod
    def get_input_connector_instances_by_workflow(
        workflow_id: str,
    ) -> list[ConnectorInstance]:
        """Method to get connector instances by workflow.

        Args:
            workflow_id (str)

        Returns:
            list[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id, ConnectorInstance.ConnectorType.INPUT
        )

    @staticmethod
    def get_output_connector_instances_by_workflow(
        workflow_id: str,
    ) -> list[ConnectorInstance]:
        """Method to get output connector instances by workflow.

        Args:
            workflow_id (str): _description_

        Returns:
            list[ConnectorInstance]: _description_
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id, ConnectorInstance.ConnectorType.OUTPUT
        )

    @staticmethod
    def get_file_system_input_connector_instances_by_workflow(
        workflow_id: str, values: Optional[list[str]] = None
    ) -> list[ConnectorInstance]:
        """Method  to fetch file system connector by workflow.

        Args:
            workflow_id (str):
            values (Optional[list[str]], optional)

        Returns:
            list[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id,
            ConnectorInstance.ConnectorType.INPUT,
            ConnectorInstance.ConnectorMode.FILE_SYSTEM,
            values,
        )

    @staticmethod
    def get_file_system_output_connector_instances_by_workflow(
        workflow_id: str, values: Optional[list[str]] = None
    ) -> list[ConnectorInstance]:
        """Method to get file system output connector by workflow.

        Args:
            workflow_id (str)
            values (Optional[list[str]], optional)

        Returns:
            list[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id,
            ConnectorInstance.ConnectorType.OUTPUT,
            ConnectorInstance.ConnectorMode.FILE_SYSTEM,
            values,
        )

    @staticmethod
    def get_database_input_connector_instances_by_workflow(
        workflow_id: str, values: Optional[list[str]] = None
    ) -> list[ConnectorInstance]:
        """Method to fetch input database connectors by workflow.

        Args:
            workflow_id (str)
            values (Optional[list[str]], optional)

        Returns:
            list[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id,
            ConnectorInstance.ConnectorType.INPUT,
            ConnectorInstance.ConnectorMode.DATABASE,
            values,
        )

    @staticmethod
    def get_database_output_connector_instances_by_workflow(
        workflow_id: str, values: Optional[list[str]] = None
    ) -> list[ConnectorInstance]:
        """Method to fetch output database connectors by workflow.

        Args:
            workflow_id (str)
            values (Optional[list[str]], optional)

        Returns:
            list[ConnectorInstance]
        """
        return ConnectorInstanceHelper.get_connector_instances_by_workflow(
            workflow_id,
            ConnectorInstance.ConnectorType.OUTPUT,
            ConnectorInstance.ConnectorMode.DATABASE,
            values,
        )

    @staticmethod
    def get_input_output_connector_instances_by_workflow(
        workflow_id: str,
    ) -> list[ConnectorInstance]:
        """Method to fetch input and output connectors by workflow.

        Args:
            workflow_id (str)

        Returns:
            list[ConnectorInstance]
        """
        filter_params: dict[str, Any] = {
            "workflow": workflow_id,
        }
        connector_instances = ConnectorInstance.objects.filter(**filter_params).all()
        return list(connector_instances)
