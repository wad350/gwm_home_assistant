"""Common utilities for GWM Car Info integration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from homeassistant.util import dt as dt_util


def format_timestamp_local(timestamp: Optional[int]) -> str | None:
    """Format millisecond timestamp to local time string.

    Returns None if timestamp is falsy or invalid.
    """
    if not timestamp:
        return None
    try:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        local_dt = dt_util.as_local(dt)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

