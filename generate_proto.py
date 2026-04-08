"""Generate Python gRPC stubs from .proto files."""

from pathlib import Path
import sys

from grpc_tools import protoc
import grpc_tools

PROTO_DIR = "../protos/proto"
OUT_DIR = "src/generated"
WKT_DIR = str(Path(grpc_tools.__file__).parent / "_proto")

PROTO_FILES = [
    f"{PROTO_DIR}/projects/v1/projects.proto",
    f"{PROTO_DIR}/projects/v1/envs.proto",
    f"{PROTO_DIR}/projects/v1/deploy_configs.proto",
    f"{PROTO_DIR}/projects/v1/vars.proto",
]

sys.exit(protoc.main([
    "grpc_tools.protoc",
    f"-I{PROTO_DIR}",
    f"-I{WKT_DIR}",
    f"--python_out={OUT_DIR}",
    f"--grpc_python_out={OUT_DIR}",
    "--experimental_editions",
    *PROTO_FILES,
]))
