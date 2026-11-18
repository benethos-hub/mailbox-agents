# The agent contract

Every agent package defines exactly one concrete `Agent` subclass in its
`agent.py`. A package under `agents/` without `agent.py` is not an agent. The class attributes are validated on instantiation.

| Attribute | Meaning |
|---|---|
| `name`, `version`, `description` | identity. `name` equals the package name |
| `triggers` | the feed events it wants, and whether it wants the tick |
| `actions` | the actions it may take, from the list below |
| `limits` | model calls per message and per day |
| `requires` | settings that must be present before it starts |
| `default_keyword` | the keyword it sets when `MAILBOX_AGENT_KEYWORD` is unset |
| `prompt_version` | the version of the prompt its model step runs under |

| Method | Meaning |
|---|---|
| `select(event)` | whether this event concerns the agent, and its route: `decide` or `observe`. Code only |
| `admit(message)` | after the fetch, whether the message is one for the agent, such as one in the inbox. Code only |
| `baseline(message)` | the question answered by rules |
| `decide(message, context)` | the question answered with the model, within the limits |
| `effect(decision, message, context)` | the actions that follow from a decision |
| `observe(message, context)` | for an event routed to `observe`: the actions it calls for, no model |
| `tick(now, context)` | for agents with deadlines: what is due |
| `prepare()` | reads what the agent needs beyond its settings, such as a list in a file |
| `backfill_folder(folder)` | whether `backfill` takes up the messages of this folder besides the inbox and sent mail. No folder by default |
| `folders_needed()` | the folders its configuration names and expects to be there, which `status` looks up. None by default |
| `may_create(path)` | whether the runtime may make the folder at `path` for it: one its configuration names. Code only, no folder by default |
| `summarize(shown)` | for `report`: lines about the messages shown, each given as sender, decision and its actions with whether each was carried out |

An event routed to `decide` makes the message `pending` and runs the steps
of [runtime](runtime.md) once per message, prompt version and model. An event routed to
`observe` is one that may come many times for one message, such as an
update of its flags. It is fetched and handed to `observe` at once.

The `context` is all an agent reaches while it works: the model, as one call
with a schema that the runtime counts, records and keeps the content of for
the evidence check, the mailbox read-only, and its open items. An agent never
holds the mailbox client, the gateway client or the state file.

The actions that exist:

| Action | Reversible by |
|---|---|
| `add_keyword` | `remove_keyword` |
| `remove_keyword` | `add_keyword` |
| `move_to_folder` | a move back, the previous folder is recorded |
| `create_folder` | none by an agent: deleting a folder needs a right no agent has. The owner removes an empty one |

An agent declares which of them it uses, and the runtime carries out no
other. A new action is added here first, with how it is taken back.

The runtime carries out an action only on these terms: it is declared, a
keyword is the agent's own, a move goes into a folder that exists and is
neither the trash, junk or spam nor below them, the message itself is
not in one of them, and the account is one the agent works on. A folder
is made only when the agent's `may_create` answers yes for its path, the
folder above it exists and is none of those three nor below them, and no
folder of the same name exists in another case. A folder below a missing
one is made after it, each as an action of its own, recorded under the
message whose move needs it. `create_folder` is the one action without a
reverse of its own. It is accepted because it changes no message
(decided 2026-11-18). An
action whose result is already there is not taken again. What the stage
does not allow is recorded as what would have been done, and so is an
action the agent asks to be `held`, whatever the stage: for a group of
[sorting](agents/sorting.md) whose folder would lend a forged mail trust.
A folder recorded and not made counts as there for the folder and the move
below it in the same effect, so a stage that records only records all
three.

**A message is moved at most once by one agent (decided 2026-11-18).** A
move of a message the agent has moved before is refused, so a message the
owner moved back, into the inbox or anywhere, stays where the owner put it,
also when `backfill --again` takes it up anew. A move only recorded in
`shadow` or `keyword` does not count. A message moved by hand never wanders
back in a later pass. The actions of one message are taken in order, and
after a refused move or folder the rest are not taken, so a keyword that
says a message was moved never stands without the move.

`status` reports for each agent whether it is ready and which required
setting is missing, without starting it. For a ready agent that names
folders it expects, it looks them up in the mailbox service, in each
account the settings name, and names each one missing.
