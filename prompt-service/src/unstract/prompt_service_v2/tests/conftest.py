import pytest
from dotenv import load_dotenv
from flask import Flask
from unstract.prompt_service_v2.controllers.extraction_controller import extraction_bp
from unstract.prompt_service_v2.controllers.indexing_controller import indexing_bp

# Load test environment variables
load_dotenv(".env.test")


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(indexing_bp)
    app.register_blueprint(extraction_bp)
    app.config.update({"TESTING": True, "DEBUG": True, "PROPAGATE_EXCEPTIONS": True, "WTF_CSRF_ENABLED": True})
    with app.test_client() as client:
        yield client
    # TODO Add teardown code here
