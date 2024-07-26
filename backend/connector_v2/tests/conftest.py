import pytest
from django.core.management import call_command


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker):  # type: ignore
    fixtures = ["./connector/tests/fixtures/fixtures_0001.json"]
    with django_db_blocker.unblock():
        call_command("loaddata", *fixtures)
