import pytest

from captcha_solver.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        captcha_api_key="test-key",
        captcha_poll_interval=0,  # disable real delay in tests
        captcha_poll_max_tries=5,
    )
