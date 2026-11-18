# Upstream: the mailbox service

The agents use the service's REST API through `benethos-mailbox-client`.
Operation names below are the service's `operationId`s.

| Need | Operation |
|---|---|
| What changed since the last look | `list_all_changes` with a state token |
| A message, its text and attachment list | `get_message` |
| The conversation a message belongs to | `get_thread` |
| Set or remove a keyword, move to a folder | `update_message` |
| The folders of an account | `list_folders` |
| Make a folder, below a parent or at the top | `create_folder` |
| The messages received since a day, for `backfill` | `list_all_messages`, once for the inbox and once for sent mail |
| The messages of one folder since a day, for `backfill` | `list_messages` of one account, the folder by its id |
| The accounts to look in for those folders, and for the folders `status` checks, without `ACCOUNTS` | `get_me` |

`sources/mailbox.py` offers these and nothing else: no send, no delete, no
trash. Which folder an agent may make is the runtime's to decide
([agent contract](agent-contract.md)). A move sets the message's folders to
the one target. A message without a text body is read with an empty text
**(to verify: whether the service always converts an HTML-only message)**.
`list_all_messages` without a folder lists the inbox alone (measured
2026-11-17 against 0.7.5), so a backfill names each folder role it wants.

What the agents rely on:

- The feed names created, updated, deleted and sent messages by id and
  answers with a new state token. A token older than the service keeps
  changes for answers `410 changes_expired`.
- The feed may name a change more than once. Every step is therefore
  idempotent ([runtime](runtime.md)).
- The text of a message arrives already converted, with hidden HTML content
  dropped.
- A change of flags made in another mail client reaches the feed only where
  the provider reports it, for IMAP with CONDSTORE. `awaiting_reply` depends
  on this ([awaiting reply](agents/awaiting_reply.md)).
- Keywords are not available on every provider **(to verify per account
  before an agent is switched to the keyword stage)**.

Folders and moves, measured 2026-11-18 against 0.7.5 with IMAP at
Stalwart, on the test account:

- A move through `update_message` keeps the message's id. The feed names
  it as `message.updated` of that id, once per move.
- `create_folder` makes a folder at the top without a parent, and below
  another with the parent's id. At IMAP a folder's id follows its path.
- A name that exists in the same case is refused, `409 conflict`. The same
  name in another case is made as a second folder beside the first, as IMAP
  names differ by case. So the runtime compares names ignoring case itself
  before it makes one.
- `delete_folder` is refused, `403 forbidden`, to a user with `mail.read`
  and `mail.write`. A folder an agent made is removed by the owner.
- A folder deleted or renamed at IMAP is no longer listed by its old id.
  A move through `update_message` to that id answers `404 not_found`,
  the same status and code as a message that is gone, and the message
  stays where it was. `create_folder` below a parent deleted so answers
  `404 not_found` as well. So the runtime reads the folders anew before
  the folders and the move of a message, and after such an answer to a
  folder or a move it asks for the message again: when it answers, the
  action is refused, and the message is not ended as gone.
- A message that arrives straight in a folder other than the inbox, as one
  a mail server files by a rule of its own, reaches the feed as
  `message.created`, here about 20 seconds after it arrived, and is read
  in that folder.
- `list_messages` of one account lists the messages of a folder named by
  its id, with `after` for a day. Named by its path it answers
  `404 not_found`. `list_all_messages` takes a role only and answers a
  folder id with `422 validation_error`. So a backfill of a folder looks up
  the folder's id first and asks each account by itself.
- `list_messages` of a folder named, in one run of 2026-11-18, one or two
  messages that `get_message` then answered with `404`: messages moved out
  of that folder shortly before **(to verify why)**. The runtime takes such
  a message as gone and ends it as `skipped`.
- The feed names, while moves are synced, a message that lives for one
  sync only. Measured 2026-11-18 in two runs of `live/invoices.py`:
  `sorting` moved four messages out of the inbox, and the feed then named
  each moved message as `message.updated` under its own id, once per sync
  of the service, roughly every 35 seconds. Beside them, in each run, two
  ids that no listing of the account had named before came as
  `message.created`, each named
  `message.deleted` in the next sync, 34 to 38 seconds later.
  `invoices` read both changes in one pass after `sorting` was done, took
  the created id up, and `get_message` answered it `404`. The runtime
  logs it as `failed step fetch of message <id>: MessageGoneError` and
  ends the message as `skipped`, as for any message deleted before it is
  read, and nothing is decided or done. So these two warnings per run of
  the check are this behaviour of the service, not a fault of the agents.
  Whether it is the same cause as the listing above is **(to verify)**.
- `get_me` answers the agents' user exactly the one account it is
  granted, the test account (measured 2026-11-18). `list_accounts` answers it `200` with no
  account at all: it belongs to the group `accounts.read`, which an agent
  is not granted. So the accounts an agent works on come from `get_me`.
  Without `ACCOUNTS` a backfill looks in the folders of each of them, so
  an account whose inbox and sent mail are empty is not left out.

Rights. Each agent has a user of its own in the service:

| Agent | Rights | Not granted |
|---|---|---|
| `invoices` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `awaiting_reply` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `inquiries` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `sorting` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |

`mail.write` also allows moving a message to the trash and creating a
folder. The service cannot refuse those to an agent that may move mail, so
the runtime does ([safety](safety.md)). Narrowing a grant to chosen folders is
possible in the service. Whether a move between two granted folders works
under such a grant is **(to verify)**.
