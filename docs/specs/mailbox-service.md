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
| The messages received since a day, for `backfill` | `list_all_messages`, once for the inbox and once for sent mail |

`sources/mailbox.py` offers these and nothing else: no send, no delete, no
trash, no folder creation. A move sets the message's folders to the one
target. A message without a text body is read with an empty text
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

Rights. Each agent has a user of its own in the service:

| Agent | Rights | Not granted |
|---|---|---|
| `invoices` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `awaiting_reply` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `inquiries` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |

`mail.write` also allows moving a message to the trash and creating a
folder. The service cannot refuse those to an agent that may move mail, so
the runtime does ([safety](safety.md)). Narrowing a grant to chosen folders is
possible in the service. Whether a move between two granted folders works
under such a grant is **(to verify)**.
