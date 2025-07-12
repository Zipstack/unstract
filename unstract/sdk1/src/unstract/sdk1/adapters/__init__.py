import logging
from logging import NullHandler
from typing import Any

logging.getLogger(__name__).addHandler(NullHandler())

AdapterDict = dict[str, dict[str, Any]]

