"""Content hash for REST diff state — shared by both pollers.

change_poller (change_api mode) and diff_poller (polling mode) both need to answer
"has this row changed since I last published it?" for upstream APIs with no change
feed. Both hash the whole row the same way, so the helper lives here rather than
one poller reaching into the other's private namespace.

Stability matters more than speed: `sort_keys` makes the digest independent of dict
ordering, and `default=str` keeps Decimals/datetimes from raising.
"""

import hashlib
import json


def content_hash(row: dict) -> str:
    return hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
