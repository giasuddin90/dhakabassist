"""Small helpers for reading settings from the environment.

Kept dependency-free so `settings.py` stays declarative and every value has
one obvious default.
"""

import os

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


def env_str(name, default=""):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError(f"{name}={raw!r} is not a boolean")


def env_int(name, default=0):
    raw = os.environ.get(name)
    return default if raw in (None, "") else int(raw)


def env_list(name, default=None):
    raw = os.environ.get(name)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]
