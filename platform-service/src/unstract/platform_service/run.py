from typing import Any

from unstract.platform_service.config import create_app
from unstract.platform_service.extensions import db

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
