"""Entry point: `python -m captcha_solver` starts the REST server."""
import uvicorn

from captcha_solver.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "captcha_solver.api.rest:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
