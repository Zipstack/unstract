import pytest
from dotenv import load_dotenv
from flask import Flask
<<<<<<< HEAD
from unstract.prompt_service_v2.controllers.extraction_controller import extraction_bp
from unstract.prompt_service_v2.controllers.indexing_controller import indexing_bp
=======
from flask_wtf.csrf import CSRFProtect
from unstract.prompt_service_v2.controllers.extraction import extraction_bp
from unstract.prompt_service_v2.controllers.indexing import indexing_bp
>>>>>>> ba48b87454fbce979f896231e75e13a3ef7d6c34

# Load test environment variables
load_dotenv(".env.test")


@pytest.fixture
def client():
    app = Flask(__name__)
<<<<<<< HEAD
=======

>>>>>>> ba48b87454fbce979f896231e75e13a3ef7d6c34
    app.register_blueprint(indexing_bp)
    app.register_blueprint(extraction_bp)
    app.config.update(
        {
            "TESTING": True,
            "DEBUG": True,
            "PROPAGATE_EXCEPTIONS": True,
<<<<<<< HEAD
            "WTF_CSRF_ENABLED": True,
        }
    )
=======
            "WTF_CSRF_ENABLED": False,
        }
    )
    csrf = CSRFProtect()
    csrf.init_app(app)  # Compliant
>>>>>>> ba48b87454fbce979f896231e75e13a3ef7d6c34
    with app.test_client() as client:
        yield client
    # TODO Add teardown code here
