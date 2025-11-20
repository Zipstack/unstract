# Flipt gRPC Client

A Python gRPC client for Flipt server-side feature flag evaluation.

## Overview

This gRPC client allows you to evaluate feature flags by communicating directly with a Flipt server via gRPC. It supports both flag evaluation operations and management operations like listing flags.

## Features

- **Flag Evaluation**: Boolean and Variant flag evaluation
- **Batch Evaluation**: Evaluate multiple flags in a single request
- **List Flags**: Retrieve all flags from a namespace
- **Secure Connections**: Support for TLS/SSL and authentication
- **Context Manager**: Automatic resource cleanup

## Installation

This is a standalone module. Copy the entire `flipt_grpc/` folder into your project and install dependencies:

```bash
pip install grpcio grpcio-tools protobuf
```

## Quick Start

```python
from flipt_grpc.client import FliptGrpcClient, GrpcClientOptions

# Create a client
client = FliptGrpcClient(
    opts=GrpcClientOptions(
        address="localhost:9000",
        namespace_key="default",
        environment_key="production"
    )
)

# Evaluate a boolean flag
result = client.evaluate_boolean(
    flag_key="my-feature",
    entity_id="user-123",
    context={"region": "us-west"}
)

print(f"Feature enabled: {result.enabled}")

# Always close the client
client.close()
```

## Configuration

### GrpcClientOptions

- `address` (str): The address of the Flipt gRPC server (default: "localhost:9000")
- `namespace_key` (str): The namespace to use for evaluations (default: "default")
- `environment_key` (str): The environment to use for evaluations (default: "default")
- `secure` (bool): Whether to use TLS/SSL for the connection (default: False)
- `client_token` (str, optional): Client token for authentication
- `ssl_cert_path` (str, optional): Path to SSL certificate for secure connections

## Usage Examples

### Boolean Flag Evaluation

```python
from flipt_grpc.client import FliptGrpcClient, GrpcClientOptions

client = FliptGrpcClient(opts=GrpcClientOptions(address="localhost:9000"))

result = client.evaluate_boolean(
    flag_key="enable-feature-x",
    entity_id="user-456",
    context={"plan": "premium", "region": "us-east"}
)

print(f"Enabled: {result.enabled}")
print(f"Reason: {result.reason}")
print(f"Duration: {result.request_duration_millis}ms")

client.close()
```

### Variant Flag Evaluation

```python
result = client.evaluate_variant(
    flag_key="color-theme",
    entity_id="user-789",
    context={"device": "mobile"}
)

print(f"Variant: {result.variant_key}")
print(f"Attachment: {result.variant_attachment}")
```

### List Flags

```python
# List all flags in the namespace
result = client.list_flags(limit=10)

print(f"Total flags: {result.total_count}")
for flag in result.flags:
    print(f"  - {flag.key}: {flag.name} (enabled: {flag.enabled})")
```

### Batch Evaluation

Evaluate multiple flags in a single request:

```python
batch_requests = [
    {
        "flag_key": "feature-a",
        "entity_id": "user-123",
        "context": {"role": "admin"}
    },
    {
        "flag_key": "feature-b",
        "entity_id": "user-123",
        "context": {"role": "admin"}
    }
]

result = client.evaluate_batch(requests=batch_requests)

for response in result.responses:
    if response.HasField("boolean_response"):
        print(f"Flag: {response.boolean_response.flag_key}, Enabled: {response.boolean_response.enabled}")
    elif response.HasField("variant_response"):
        print(f"Flag: {response.variant_response.flag_key}, Variant: {response.variant_response.variant_key}")
```

### Context Manager

Use the context manager for automatic cleanup:

```python
with FliptGrpcClient(opts=GrpcClientOptions(address="localhost:9000")) as client:
    result = client.evaluate_boolean("my-flag", "user-123")
    print(result.enabled)
# Client is automatically closed
```

### Secure Connection with Authentication

```python
client = FliptGrpcClient(
    opts=GrpcClientOptions(
        address="flipt.example.com:443",
        namespace_key="production",
        secure=True,
        client_token="your-client-token"
    )
)

result = client.evaluate_boolean("secure-flag", "user-secure")
client.close()
```

### Custom SSL Certificate

```python
client = FliptGrpcClient(
    opts=GrpcClientOptions(
        address="flipt.internal:9000",
        secure=True,
        ssl_cert_path="/path/to/ca-cert.pem"
    )
)
```

## Error Handling

The client raises `grpc.RpcError` for gRPC-related errors:

```python
import grpc

try:
    result = client.evaluate_boolean("my-flag", "user-123")
except grpc.RpcError as e:
    print(f"gRPC error: {e.code()}")
    print(f"Details: {e.details()}")
```

## Architecture

This client uses two gRPC services:

1. **`flipt.evaluation.EvaluationService`** - For flag evaluation operations:
   - `Boolean()` - Boolean flag evaluation
   - `Variant()` - Variant flag evaluation
   - `Batch()` - Batch evaluation

2. **`flipt.Flipt`** - For management operations:
   - `ListFlags()` - List all flags in a namespace

## File Structure

```
flipt_grpc/
├── __init__.py
├── client.py                          # Main client implementation
├── README.md                          # This file
├── CLAUDE.md                          # AI assistant instructions
├── proto/                             # Proto source files
│   └── flipt/
│       ├── flipt_simple.proto         # Flipt service definition
│       └── evaluation/
│           └── evaluation_simple.proto # Evaluation service definition
└── flipt/                             # Generated gRPC code
    ├── __init__.py
    ├── flipt_simple_pb2.py            # Flipt messages
    ├── flipt_simple_pb2_grpc.py       # Flipt service stub
    └── evaluation/
        ├── __init__.py
        ├── evaluation_simple_pb2.py   # Evaluation messages
        └── evaluation_simple_pb2_grpc.py # Evaluation service stub
```

## Regenerating gRPC Code

If you need to regenerate the gRPC code from the proto files:

```bash
# From the parent directory of flipt_grpc/
python -m grpc_tools.protoc \
  -I./flipt_grpc/proto \
  --python_out=./flipt_grpc \
  --grpc_python_out=./flipt_grpc \
  flipt_grpc/proto/flipt/flipt_simple.proto

python -m grpc_tools.protoc \
  -I./flipt_grpc/proto \
  --python_out=./flipt_grpc \
  --grpc_python_out=./flipt_grpc \
  flipt_grpc/proto/flipt/evaluation/evaluation_simple.proto
```

Then fix the imports in the generated `*_grpc.py` files to use relative imports:

```python
# Change this:
from flipt import flipt_simple_pb2
# To this:
from . import flipt_simple_pb2
```

## Server Configuration

Make sure your Flipt server has gRPC enabled. The default gRPC port is 9000.

In your Flipt configuration:

```yaml
server:
  grpc:
    enabled: true
    port: 9000
```

## Verifying Server Capabilities

Use `grpcurl` to verify what methods your Flipt server supports:

```bash
# List all services
grpcurl -plaintext localhost:9000 list

# List methods in evaluation service
grpcurl -plaintext localhost:9000 list flipt.evaluation.EvaluationService

# List methods in Flipt service
grpcurl -plaintext localhost:9000 list flipt.Flipt

# Test ListFlags
grpcurl -plaintext -d '{"namespace_key": "default", "environment_key": "default", "limit": 10}' \
  localhost:9000 flipt.Flipt/ListFlags
```

## Important Notes

- **`ListFlags` requires `environment_key`**: The Flipt server requires the `environment_key` parameter for `ListFlags`. If not provided, it will default to the value in `GrpcClientOptions`.
- **Proto files are optional at runtime**: The `.proto` files are only needed for regeneration. The generated `*_pb2.py` files contain all runtime logic.
- **Two separate stubs**: The client maintains two gRPC stubs - one for evaluation operations and one for management operations.

## License

MIT License - see LICENSE file for details.
