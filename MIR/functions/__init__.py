"""Closed native-function surface for RIF.

Dynamic Python callbacks are intentionally not part of this package. Native
functions are explicit modules with primitive contracts suitable for a C
backend.
"""

from .calc import CalcError, INT64_MAX, INT64_MIN, MAX_WIDTH, calc
from .reqsts import MAX_REQSTS_BYTES, REQSTS_TIMEOUT_SECONDS, ReqstsError, reqsts
from ..operations import (
    OperationError,
    OperationSpec,
    RULE_OPERATION_ABI_VERSION,
    execute_operation,
    operation_abi,
    operation_abi_json,
    operation_c_header,
    operation_c_source,
    operation_specs,
)

__all__ = [
    "CalcError",
    "INT64_MAX",
    "INT64_MIN",
    "MAX_WIDTH",
    "MAX_REQSTS_BYTES",
    "REQSTS_TIMEOUT_SECONDS",
    "ReqstsError",
    "calc",
    "reqsts",
    "OperationError",
    "OperationSpec",
    "RULE_OPERATION_ABI_VERSION",
    "execute_operation",
    "operation_abi",
    "operation_abi_json",
    "operation_c_header",
    "operation_c_source",
    "operation_specs",
]
