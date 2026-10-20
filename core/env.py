"""Small helpers for reading settings from the environment.

Kept dependency-free so `settings.py` stays declarative and every value has
one obvious default. A blank value (`NAME=` in `.env`) counts as unset.
"""

import os

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def env_str(name, default=""):
    """Return the variable, or `default` when it is unset or blank."""
    return os.environ.get(name, "").strip() or default


def env_bool(name, default=False):
    """Read 1/0, true/false, yes/no or on/off; anything else is an error."""
    raw = env_str(name).lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError(f"{name}={raw!r} is not a boolean")


def env_list(name, default=None):
    """Split a comma-separated value, dropping empty items."""
    raw = env_str(name)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]
