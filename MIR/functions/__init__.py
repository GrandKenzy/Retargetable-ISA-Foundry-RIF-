"""Closed native-function surface for RIF.

Dynamic Python callbacks are intentionally not part of this package. Native
functions are explicit modules with primitive contracts suitable for a C
backend.
"""

from .calc import CalcError, INT64_MAX, INT64_MIN, MAX_WIDTH, calc
from .reqsts import MAX_REQSTS_BYTES, REQSTS_TIMEOUT_SECONDS, ReqstsError, reqsts

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
]
