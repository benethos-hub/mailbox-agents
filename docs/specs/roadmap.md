# Roadmap and open questions

| Phase | Content |
|---|---|
| 0 | Package, CI, settings, contract, store with migrations |
| 1 | Runtime: feed, tick, steps, actions, health, metrics, with an agent that only counts |
| 2 | `invoices`: gold set, baseline, model, first report, then `keyword`, then `full` |
| 3 | `awaiting_reply` |
| 4 | `inquiries`: label, then fields |
| 4b | `sorting`: groups of senders to folders by rules alone, the action `create_folder`, then `invoices` rebuilt to look in folders named at its start and to move an invoice into a subfolder ([sorting](agents/sorting.md), [invoices](agents/invoices.md), planned 2026-11-18) |
| 5 | Recognising a repeated inquiry by embeddings, stored in the state file |
| 6 | Handing a message to an external agent server over HTTP, and reply drafts |
| 7 | A daily overview of what every agent did, read from the state files by a process of its own, with no model involved |

Ideas not scheduled: newsletters to a folder by the `List-Unsubscribe`
header, a keyword for mail that names a deadline, a mark for mail from
authorities.

## Open questions

1. **How the daily overview reaches the owner.** A mail to the owner's own
   address, from a user that may send there and nowhere else, or a draft.
   Not decided, the overview is phase 7.
2. **Keywords per provider.** [mailbox service](mailbox-service.md), to verify per account. Measured
   2026-11-17 for IMAP at Stalwart through the service 0.7.5: a keyword is
   set and taken off, and a move to another folder keeps the message's id
   and is taken back by a move to the folder before. Measured 2026-11-18:
   a keyword set as `Awaiting-Reply` comes back as `awaiting-reply`, so
   the runtime and the agents compare keywords without case. Other
   providers are still to verify.
3. **Folder-narrowed grants and moves.** [mailbox service](mailbox-service.md), to verify. It decides
   whether the grant of `invoices` can be narrowed to the inbox and the
   parent folder of [invoices](agents/invoices.md).
4. **Automatic answers.** The service exposes no header of a message
   (measured 2026-11-17 against 0.7.5), so `Auto-Submitted` cannot be read.
   `awaiting_reply` uses a heuristic on sender and subject (decided
   2026-11-17) and the evaluation counts what it misses.

Answered, all on 2026-11-17:

- **Licence.** MIT.
- **What `invoices` covers.** [invoices](agents/invoices.md): invoices and invoice notices
  from suppliers, one folder per listed supplier, others marked only.
- **Order of the agents.** `invoices`, `awaiting_reply`, `inquiries`.
- **Metrics.** The `prometheus-client` package.
- **Settings.** pydantic-settings.
- **Sync or async.** asyncio.
- **A report command.** Yes, [runtime](runtime.md).
- **The test setup for live checks.** `containers/live/`, [testing](testing.md).
- **Schema through the gateway.** It reaches a local backend, [model gateway](model-gateway.md).
