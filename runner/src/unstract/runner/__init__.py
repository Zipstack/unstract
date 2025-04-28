import logging
import os

from flask import Flask

from unstract.core.flask import register_error_handlers, register_request_id_middleware
from unstract.core.flask.logging import setup_logging
from unstract.runner.constants import LogLevel
from unstract.runner.runner import UnstractRunner

from .controller import api

app = Flask(__name__)

# Configure logging
log_level = os.getenv("LOG_LEVEL", LogLevel.INFO).upper()
log_level = getattr(logging, log_level, logging.INFO)
setup_logging(log_level)

# Register error handlers
register_error_handlers(app)

# Register middleware
register_request_id_middleware(app)

# Register URL routes
app.register_blueprint(api)

__all__ = ["UnstractRunner"]
