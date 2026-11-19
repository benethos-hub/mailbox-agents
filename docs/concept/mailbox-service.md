# Concept: the mailbox service

Part of the [concept](../CONCEPT.md).

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
| The version of the service, before every pass and every backfill | `health` |

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
  on this ([awaiting reply](agent-awaiting-reply.md)).
- Keywords are not available on every provider **(to verify per account
  before an agent is switched to the keyword stage)**.

Folders and moves, measured 2026-11-18 against 0.7.5 with IMAP at
Stalwart, on the test account:

- A move through `update_message` keeps the message's id. The feed names
  it as `message.updated` of that id, once per move.
- A move made by a mail client over IMAP keeps the message's id as well
  (measured 2026-11-19 against 0.7.5, for the plan of
  [invoices](agent-invoices.md) version 5). One message was moved out of
  the inbox into a folder made for the check and back, once with `MOVE`
  and once with `COPY`, `\Deleted` and `EXPUNGE`, as clients without
  `MOVE` do. Each way the feed named only `message.updated` of the same
  id, within one sync, no `message.created` and no `message.deleted`.
  `get_message` read it under that id in its new folder, and a keyword
  set before the move went with it. So the state file of an agent knows a
  message a person moves by hand, and its open item follows it. A message
  under an id no state file knows, but with an agent's keyword, comes from
  a state file made anew, or from a provider that gives a moved message a
  new id, which this check did not see at Stalwart.
- A message moved and moved back can come back under another id, measured
  2026-11-19 in four runs of `live/invoices.py`. `sorting` moved four
  messages of the inbox into its folders, three of them into
  `Providers/CloudHost`, and the check moved all four back through
  `update_message` some minutes later. Afterwards two of the three in
  `Providers/CloudHost`, each time the same two and none of them an
  invoice, were no longer read under their old id (`404`) and lay in the
  inbox under a new one. The two short-lived ids the feed names while
  moves sync (below) came in the same runs. Moving those three messages
  into that folder and back through the service by a script, one after
  the other with a keyword set and taken off, kept every id, as did a
  single message moved alone. What gives the new id is **(to verify)**.
  An agent that relies on its state file meets such a message as a new
  one: `invoices` skips it when it carries the agent's keyword, and asks
  about it when it does not.
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

## The version of the service

The service names its version at `/health`, which it answers without a
right and counts against no limit. While its major version is 0, a minor
release may change what it does and what its interface takes, and the
offline suite sees none of that: it mocks the service. So the agents work
only against the lines they were tested against (decided 2026-11-19).

- **A line** is the minor version while the major is 0, such as 0.7, and
  the major version from 1 on. It starts at the lowest release that was
  tested, and every later release of it counts as tested.
- **The lines** are `TESTED` in `sources/mailbox.py`, the newest last.
  Today there is one: 0.7 from 0.7.5. The newest line is also the pin of
  `benethos-mailbox-client` in `pyproject.toml` and the line of the image
  in `containers/live/compose.yaml`, and `README.md` names the lines with
  a link to the service. A test holds the four equal.
- **The check.** The worker asks the service for its version before every
  pass and every backfill. A service outside the lines, or one that names
  no version, ends the command with a `ServiceVersionError` and exit code
  2, before the feed is read: nothing is read, decided or changed. It is
  asked in every pass and not only at the start, since a service can be
  replaced by another release between two passes without one request
  failing.
- **In every stage, with no setting to pass it.** The stage `shadow` is
  refused as well: what it records would be read from a service nobody
  measured. A warning alone would go unread in a process that runs for
  weeks.
- **`status`** names the version of the service and whether it is tested,
  and starts no agent.
- **The client is not compared with the service.** Within a line the
  installed client may be older or newer than the service, and the agents
  run: a patch release of the service is taken to change no interface.
  The pin `~=X.Y.Z` keeps the client in the line, from its lowest tested
  release on. A pin to one exact release of both was decided against
  (2026-11-19): after every patch release of the service no agent would
  start until a release of the agents followed. A patch release that
  changes what the service does after all is not seen by the check. The
  live checks are there for it, run when the client or the image of the
  live setup is raised.

What follows from it: while the service is at 0.x, each of its minor
releases needs a release of the agents before the two work together. So
that the agents can be updated first and the service after them, a
release of the agents may hold two lines for a time, the old and the new.

A new line is a change of its own, in this order:

1. Read the changelog of the service from the last tested release to the
   new one, its breaking changes and its fixes, against this file: each
   statement here that carries a date and a version, and each one marked
   **(to verify)**.
2. Raise the image of `containers/live/compose.yaml`, tag and digest, set
   the live setup up anew and run the live checks of
   [testing](testing.md) against it.
3. Measure again what step 1 found changed, and write the result here
   with its date and the version. A statement that no longer holds goes.
4. Add the line to `TESTED`, raise the pin of the client and name the
   line in `README.md`, all in the same commit, with an entry in
   `CHANGELOG.md` that names the service the release needs. The old line
   leaves `TESTED` once the code relies on something only the new one
   does.

A later release within a tested line needs none of this. Dependabot
raises the client in `uv.lock` and the image of the live setup each in a
pull request of its own, and each wants a run of the live checks.

An agent does not go back to the stage `shadow` because of a new line
(decided 2026-11-19): its prompt and its model are the same, and the live
checks on the test account are the gate for the service.
