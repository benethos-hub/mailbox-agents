"""The schema of a state file, as numbered migrations.

Migration ``n`` is ``MIGRATIONS[n - 1]``, and a file's ``user_version``
says how many have run. **A migration is never changed once released.** A
change of the schema is a new entry at the end. SPECS.md section 9 names
the tables.

Times are ISO 8601 text in UTC. A message is named by its account id and
its message id together, as the mailbox service names it.
"""

from __future__ import annotations

__all__ = ["MIGRATIONS"]

_FIRST = """
CREATE TABLE cursor (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL,
    updated TEXT NOT NULL
);

CREATE TABLE passes (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    finished TEXT NOT NULL
);

CREATE TABLE messages (
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('pending', 'skipped', 'decided', 'done', 'failed')
    ),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    PRIMARY KEY (account_id, message_id)
);
CREATE INDEX messages_by_state ON messages (state, next_attempt);

CREATE TABLE steps (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    step TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    model TEXT NOT NULL,
    result TEXT NOT NULL,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
CREATE INDEX steps_by_message ON steps (
    account_id, message_id, step, prompt_version, model_alias
);
CREATE INDEX steps_by_time ON steps (step, at);

CREATE TABLE actions (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    action TEXT NOT NULL,
    argument TEXT NOT NULL,
    before TEXT NOT NULL,
    stage TEXT NOT NULL,
    executed INTEGER NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX actions_by_message ON actions (account_id, message_id);

CREATE TABLE open_items (
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT,
    opened TEXT NOT NULL,
    due TEXT NOT NULL,
    keyword_set INTEGER NOT NULL DEFAULT 0,
    closed TEXT,
    reason TEXT,
    PRIMARY KEY (account_id, message_id)
);
CREATE INDEX open_items_by_thread ON open_items (account_id, thread_id);
CREATE INDEX open_items_by_due ON open_items (closed, due);

CREATE TABLE calls (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    request TEXT NOT NULL,
    answer TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX calls_by_time ON calls (at);
"""

# The stage in which the keyword of an item was recorded without being set,
# so shadow records an item once and a later stage sets it.
_SECOND = """
ALTER TABLE open_items ADD COLUMN keyword_recorded_stage TEXT;
"""

MIGRATIONS: tuple[str, ...] = (_FIRST, _SECOND)
