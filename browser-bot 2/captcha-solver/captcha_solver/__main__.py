"""Entry point: `python -m captcha_solver` starts the REST server."""
import logging
import uvicorn

from captcha_solver.config import get_settings


def main() -> None:
    # Root-logger чтобы наши captcha_solver.* логи попадали в stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = get_settings()
    uvicorn.run(
        "captcha_solver.api.rest:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
