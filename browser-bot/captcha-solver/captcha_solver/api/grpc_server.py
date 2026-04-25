"""gRPC wrapper — same core solver as REST.

Generate stubs before running:

    python -m grpc_tools.protoc \\
        -I proto \\
        --python_out=captcha_solver/proto \\
        --grpc_python_out=captcha_solver/proto \\
        proto/captcha.proto

Then: `python -m captcha_solver.api.grpc_server`.
"""
from __future__ import annotations

import asyncio
import logging

import grpc

from captcha_solver.config import get_settings
from captcha_solver.solver import CaptchaSolver, CaptchaType

logger = logging.getLogger(__name__)

try:
    from captcha_solver.proto import captcha_pb2, captcha_pb2_grpc
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "gRPC stubs not generated. Run:\n"
        "  python -m grpc_tools.protoc -I proto "
        "--python_out=captcha_solver/proto "
        "--grpc_python_out=captcha_solver/proto proto/captcha.proto"
    ) from e


_PB_TO_TYPE = {
    captcha_pb2.CAPTCHA_TYPE_UNSPECIFIED: None,
    captcha_pb2.CAPTCHA_TYPE_NONE: CaptchaType.NONE,
    captcha_pb2.CAPTCHA_TYPE_CLICK: CaptchaType.CLICK,
    captcha_pb2.CAPTCHA_TYPE_COORDINATE: CaptchaType.COORDINATE,
}
_TYPE_TO_PB = {v: k for k, v in _PB_TO_TYPE.items() if v is not None}


class CaptchaSolverService(captcha_pb2_grpc.CaptchaSolverServicer):
    def __init__(self) -> None:
        self._solver = CaptchaSolver()

    async def Solve(  # noqa: N802 - gRPC generated name
        self,
        request: captcha_pb2.SolveRequest,
        context: grpc.aio.ServicerContext,
    ) -> captcha_pb2.SolveResponse:
        force = _PB_TO_TYPE.get(request.force_type)
        result = await self._solver.solve(request.url, force_type=force)
        return captcha_pb2.SolveResponse(
            type=_TYPE_TO_PB.get(result.type, captcha_pb2.CAPTCHA_TYPE_UNSPECIFIED),
            solved=result.solved,
            token=result.token,
            coordinates=[captcha_pb2.Coordinate(x=c.x, y=c.y) for c in result.coordinates],
            duration_seconds=result.duration_seconds,
            error=result.error,
        )

    async def Healthz(  # noqa: N802
        self,
        request: captcha_pb2.HealthzRequest,
        context: grpc.aio.ServicerContext,
    ) -> captcha_pb2.HealthzResponse:
        return captcha_pb2.HealthzResponse(status="ok")


async def serve() -> None:
    settings = get_settings()
    server = grpc.aio.server()
    captcha_pb2_grpc.add_CaptchaSolverServicer_to_server(CaptchaSolverService(), server)
    address = f"{settings.host}:{settings.grpc_port}"
    server.add_insecure_port(address)
    await server.start()
    logger.info("gRPC server listening on %s", address)
    await server.wait_for_termination()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
