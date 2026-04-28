#!/usr/bin/env bash
# Regenerate gRPC stubs from proto/captcha.proto
set -euo pipefail
cd "$(dirname "$0")/.."
python -m grpc_tools.protoc \
  -I proto \
  --python_out=captcha_solver/proto \
  --grpc_python_out=captcha_solver/proto \
  proto/captcha.proto
# Fix import path in generated _pb2_grpc.py to use package-relative import
python - <<'PY'
from pathlib import Path
p = Path("captcha_solver/proto/captcha_pb2_grpc.py")
s = p.read_text()
s = s.replace("import captcha_pb2 as captcha__pb2",
              "from captcha_solver.proto import captcha_pb2 as captcha__pb2")
p.write_text(s)
PY
echo "proto stubs regenerated"
