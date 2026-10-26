"""A wait between repeats of an action, kept in the visitor's session.

What a page shows ("ask again in 0:45") comes from here, so it reads the same
whether or not an account sits behind the request. The limit that matters
for an inbox is stored with the account (`User.claim_confirmation_send`).
"""

import math

from django.utils import timezone


class SessionCooldown:
    """At least `seconds` between two `start()`s, under `key` in the session."""

    def __init__(self, key, seconds):
        self.key = key
        self.seconds = seconds

    def start(self, session):
        """Begin the wait now."""
        # A timestamp, because the session is stored as JSON.
        session[self.key] = timezone.now().timestamp()

    def remaining(self, session):
        """Whole seconds left to wait; 0 once the action is allowed again."""
        started = session.get(self.key)
        if started is None:
            return 0
        left = started + self.seconds - timezone.now().timestamp()
        return max(0, math.ceil(left))


def clock(seconds):
    """Seconds as m:ss, the way a countdown reads."""
    return f"{seconds // 60}:{seconds % 60:02d}"
