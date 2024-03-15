import logging

from cron_descriptor import (
    CasingTypeEnum,
    ExpressionDescriptor,
    FormatException,
)
from cron_expression_generator.exceptions import CronDescriptionError

logger = logging.getLogger(__name__)


class CronDescriptor:
    """Describes a cron deterministically with `cron-expression-description`"""

    @staticmethod
    def describe_cron(cron: str) -> str:
        """Given a cron string, gives a human readable summary of it.

        Args:
            cron (str): Cron to summarize

        Returns:
            str: Human readable summary of the cron string
        """
        summary = ""
        logger.info(f"Describing cron: {cron}")
        try:
            descriptor = ExpressionDescriptor(
                expression=cron,
                casing_type=CasingTypeEnum.Sentence,
                use_24hour_time_format=True,
            )
            summary = descriptor.get_full_description()
        except FormatException:
            raise CronDescriptionError("Incorrect cron string format")
        return summary
