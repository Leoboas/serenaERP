"""Small, dependency-free observability primitives shared by adapters."""

import json
import logging
import sys
from typing import Any

_LOGGER_NAME = "serenaerp"


def configure_logging() -> None:
    """Emit machine-readable logs without changing third-party logger setup."""

    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {"event": event, **{key: str(value) for key, value in fields.items() if value is not None}}
    logging.getLogger(_LOGGER_NAME).log(level, json.dumps(payload, separators=(",", ":"), sort_keys=True))
