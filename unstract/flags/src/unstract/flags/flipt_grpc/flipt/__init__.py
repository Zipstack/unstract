"""Flipt gRPC protobuf definitions."""

# Pre-register the Timestamp well-known type in the protobuf descriptor pool.
# Required because flipt_simple_pb2.py and evaluation_simple_pb2.py declare
# a dependency on google/protobuf/timestamp.proto in their serialized descriptors.
# Without this, AddSerializedFile() fails with KeyError (pure-Python) or TypeError (C/upb).
# In the backend, this happens to work because Google Cloud libraries (google-cloud-storage,
# etc.) import timestamp_pb2 as a side effect during Django startup. Workers don't have
# that implicit dependency, so we must be explicit.
from google.protobuf import timestamp_pb2 as _timestamp_pb2  # noqa: F401
