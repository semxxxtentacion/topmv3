FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

COPY captcha_solver ./captcha_solver
COPY proto ./proto
COPY scripts ./scripts

# Generate gRPC stubs into the package
RUN python -m grpc_tools.protoc \
        -I proto \
        --python_out=captcha_solver/proto \
        --grpc_python_out=captcha_solver/proto \
        proto/captcha.proto && \
    sed -i 's/^import captcha_pb2 as captcha__pb2$/from captcha_solver.proto import captcha_pb2 as captcha__pb2/' \
        captcha_solver/proto/captcha_pb2_grpc.py

EXPOSE 8080 50051

ENV HEADLESS=true HOST=0.0.0.0 PORT=8080 GRPC_PORT=50051

# Default: REST. Override CMD to run gRPC:
#   docker run ... captcha-solver python -m captcha_solver.api.grpc_server
CMD ["python", "-m", "captcha_solver"]
