from typing import Any

from unstract.prompt_service_v2.config import create_app
from unstract.prompt_service_v2.extensions import db

app = create_app()


@app.before_request
def before_request() -> None:
    if db.is_closed():
        db.connect(reuse_if_open=True)


@app.teardown_request
def after_request(exception: Any) -> None:
    # Close the connection after each request
    if not db.is_closed():
        db.close()
