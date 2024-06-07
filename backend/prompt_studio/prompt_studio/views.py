import logging
from typing import Optional

from django.db.models import QuerySet
from django.http import HttpRequest
from prompt_studio.permission import PromptAcesssToUser
from prompt_studio.prompt_studio.constants import ToolStudioPromptKeys
from prompt_studio.prompt_studio.helper import PromptStudioHelper
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio.serializers import (
    ReorderPromptsSerializer,
    ToolStudioPromptSerializer,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

logger = logging.getLogger(__name__)


class ToolStudioPromptView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics.

    Args:
        viewsets (_type_)

    Raises:
        DuplicateData
        FilenameMissingError
        IndexingError
        ValidationError
    """

    versioning_class = URLPathVersioning
    serializer_class = ToolStudioPromptSerializer
    permission_classes: list[type[PromptAcesssToUser]] = [PromptAcesssToUser]

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        if filter_args:
            queryset = ToolStudioPrompt.objects.filter(**filter_args)
        else:
            queryset = ToolStudioPrompt.objects.all()
        return queryset

    @action(detail=True, methods=["post"])
    def reorder_prompts(self, request: HttpRequest) -> Response:
        """Reorder the sequence of prompts based on the start and drop sequence
        numbers.

        This action handles the reordering of prompts by updating their sequence
        numbers. It increments or decrements the sequence numbers of the relevant
        prompts to reflect the new order. If the start and drop sequence numbers
        are equal, it returns a bad request response.

        Args:
            request (HttpRequest): The HTTP request object containing the data to
            reorder prompts.

        Returns:
            Response: A Response object with the status of the reordering operation.
        """
        try:
            # Validate request data
            serializer = ReorderPromptsSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Extract validated data from the serializer
            start_sequence_number = serializer.validated_data.get(
                ToolStudioPromptKeys.START_SEQUENCE_NUMBER
            )
            end_sequence_number = serializer.validated_data.get(
                ToolStudioPromptKeys.END_SEQUENCE_NUMBER
            )
            prompt_id = serializer.validated_data.get(ToolStudioPromptKeys.PROMPT_ID)

            prompt_instance: ToolStudioPrompt = ToolStudioPrompt.objects.get(
                pk=prompt_id
            )
            filtered_prompts_data = []
            tool_id = prompt_instance.tool_id

            # Determine the direction of sequence adjustment based on start and
            # drop sequence numbers
            if start_sequence_number < end_sequence_number:
                logger.info(
                    "Start sequence number is less than drop sequence number. "
                    "Decrementing sequence numbers."
                )
                filters = {
                    "sequence_number__gt": start_sequence_number,
                    "sequence_number__lte": end_sequence_number,
                    "tool_id": tool_id,
                }
                # Call helper method to update sequence numbers and
                # get filtered prompt data
                filtered_prompts_data = PromptStudioHelper.update_sequence_numbers(
                    filters, increment=False
                )

            elif start_sequence_number > end_sequence_number:
                logger.info(
                    "Start sequence number is greater than drop sequence number. "
                    "Incrementing sequence numbers."
                )
                filters = {
                    "sequence_number__lt": start_sequence_number,
                    "sequence_number__gte": end_sequence_number,
                    "tool_id": tool_id,
                }
                # Call helper method to update sequence numbers and
                # get filtered prompt data
                filtered_prompts_data = PromptStudioHelper.update_sequence_numbers(
                    filters, increment=True
                )

            # If the start and drop sequence numbers are equal,
            # return a bad request response
            else:
                logger.warning(
                    "Start and drop sequence numbers are equal. "
                    "Returning bad request response."
                )
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data={"detail": "Start and drop sequence numbers are equal."},
                )

            # Update the sequence number of the moved prompt
            prompt_instance.sequence_number = end_sequence_number
            prompt_instance.save()
            # Append the updated prompt instance data to the response
            filtered_prompts_data.append(
                {
                    "id": prompt_instance.prompt_id,
                    "sequence_number": prompt_instance.sequence_number,
                }
            )

            logger.info("Re-ordering completed successfully.")
            return Response(status=status.HTTP_200_OK, data=filtered_prompts_data)

        except ToolStudioPrompt.DoesNotExist:
            logger.error(f"Prompt with ID {prompt_id} not found.")
            return Response(
                status=status.HTTP_404_NOT_FOUND, data={"detail": "Prompt not found."}
            )

        except Exception as e:
            logger.exception(
                f"An unexpected error occurred while re-ordering the prompts: {e}"
            )
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"detail": "An unexpected error occurred."},
            )
