import pytest

from app import create_app
from app.core.config import Config


@pytest.fixture
def client():
    Config.AUTH_ENABLED = False
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
