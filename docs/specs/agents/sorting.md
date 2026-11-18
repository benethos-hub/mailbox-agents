# The agent `sorting`

> **Status: built on 2026-11-18, steps S1 to S7, and run in `shadow` and in
> `full` on the test account. Not run on a real mailbox.** Planned the same
> day and revised after a review against the code. Its purpose: the mail of
> providers such as a shop, a hoster or a bank goes into a folder of its
> own, and one folder may take several, such as all banks. The name is a
> working name. A decision is marked with its date.

**Question:** is the sender of this message in the inbox one of a listed
group, and which folder is the group's?

| | |
|---|---|
| Triggers | `message.created` in the inbox, and `backfill` for older mail |
| Baseline | the sender rules of the list. They are the whole agent |
| Model | none |
| Actions | `move_to_folder`, `create_folder`, and `add_keyword` with the move |
| Keyword | `agent-sorted`, set with each move, see section 3 |

## 1. Two stages, two agents (decided 2026-11-18)

`sorting` moves by the sender alone, from the inbox into the group's
folder. Whether a message is an invoice is asked afterwards, by
[invoices](invoices.md), which moves it on within the folder it lies in. No
agent does both.

Each agent works without the other. `sorting` knows nothing of invoices.
`invoices` knows nothing of groups: it is told at its start which folders
it looks in ([invoices](invoices.md#settings)).

The two never compete for a message:

| Agent | Moves a message that lies in | To |
|---|---|---|
| `sorting` | the inbox | the folder of the sender's group |
| `invoices` | a folder it was told to look in, other than the inbox | the subfolder below that folder |
| `invoices`, with an inbox folder set | the inbox | the inbox folder |

So no rule about who runs first and no waiting time is needed, and both run
on one account, as long as `invoices` has no inbox folder. With one set, an
invoice `invoices` takes up first goes into that folder, and `sorting`
leaves it there.

```
Inbox
Bank/
CloudHost/
  Rechnungen/
Telco/
  Rechnungen/
```

## 2. The list

A JSON file named in `MAILBOX_AGENTS_SORTING_FILE`, not versioned. An example
of it is versioned as `sorting.example.json`.

```json
{
  "groups": [
    {"name": "Bank", "folder": "Bank",
     "senders": ["*@bank-one.example", "service@bank-two.example"],
     "hold": true},
    {"name": "CloudHost", "folder": "CloudHost",
     "senders": ["*@cloudhost.example"]}
  ]
}
```

| Field | Meaning | Rule |
|---|---|---|
| `name` | what `report` and the decision call the group | unique, case aside, no space at its ends, not `none` in any case |
| `folder` | where its mail goes, `/` between the names | unique, case aside. No name empty, `.` or `..`, nor with a space at its ends. A folder above it that another group's path shares is written alike in both |
| `senders` | who belongs to it | at least one. A rule belongs to one group |
| `hold` | section 5 | optional, `false` when left out |

The folder is chosen freely (decided 2026-11-18): one folder for several
senders, such as all banks in `Bank`, one per sender, or a folder below
another.

**A list that could never work is refused (decided 2026-11-18).** Two
groups that write one folder in two cases, `Bank` beside `bank/Sub`, would
never get the second, as the runtime makes no folder whose name exists in
another case. A group named `none` would share the label of a message in
no group, and `report` would leave it out. A domain with an empty name,
such as `*@.shop.example`, `*@shop..example` or `a@b.example.`, matches no
sender. Each is named by its group, and a rule by its place too.

### Sender rules

| Kind | Written | Covers |
|---|---|---|
| address | `service@bank-two.example` | that address |
| pattern | `*@cloudhost.example`, `mailbox*@telco.example` | every address of that domain the `*` fits. `*` stands before the `@` |
| pattern for subdomains | `*@*.shop.example` | every address of every subdomain of `shop.example`, not of `shop.example` itself |
| domain | `cloudhost.example` | refused, see below |

- Case is ignored.
- The most specific rule wins: an address before a pattern before a
  pattern for subdomains.
- Two groups whose rules of the same kind both match leave the sender
  unmatched. Nothing is guessed.
- A pattern covers one domain. The subdomains are a rule of their own,
  `*@*.domain` for all of them (decided 2026-11-18). Such a rule is no less
  trusted than `*@domain`, since the sender is not authenticated anyway,
  only broader.
- The domain after `*.` has two names at least: `*@*.example` is refused
  as too broad. Whether two names are a registered domain, such as
  `co.uk`, is not checked.

**A domain rule is refused (decided 2026-11-18).** In `invoices` today a
domain rule marks and does not move. `sorting` sets no keyword a domain
could mark with, so such a rule would do nothing. The message says to
write `*@domain` or `*@*.domain`.

### When the list is read

- Once, at the start of the agent. A wrong list stops the start and
  `status` names what is wrong. A wrong rule is named by its group and
  its place in the group's list, `group 'Bank', sender 2`, never by
  itself, as a rule often names a person (decided 2026-11-18).
- A changed list takes effect at the next start. It is new work: the
  decision is stored under a version made from the list, see section 3.
- `sorting` reads and matches it with code of its own. The supplier list
  of `invoices` version 3, whose rules differed, is gone with its rebuild
  (step I5).

## 3. What happens to a message

| The message | What happens | State |
|---|---|---|
| is not in the inbox | nothing | `skipped` |
| is in the inbox and carries the agent's keyword: a person put it back | nothing | `skipped` |
| is in the inbox, no rule matches its sender | nothing. `report` counts the sender | `done`, label `none` |
| is in the inbox, rules of two groups match alike | nothing. `report` names it as ambiguous | `done`, label `none` |
| is in the inbox, one group matches, the folder exists | a move to the folder | `done`, label the group |
| the same, the folder is missing | `create_folder`, then the move | `done`, label the group |
| the same, the group is held | the move is recorded, not made | `done`, label the group |
| is in the trash, junk or spam | nothing, as it is not in the inbox. The runtime would refuse a move of it anyway | `skipped` |

A message already in another folder is the owner's choice and stays.

**The keyword (decided 2026-11-18).** With each move the agent sets its
keyword, `agent-sorted` by default, so a message it sorted is known as such
to a person in a mail client and to a state file made anew. A message in
the inbox that carries it was put back by a person and is left alone.
Besides, the runtime moves a message at most once for an agent ([agent
contract](../agent-contract.md)). The keyword is its own and no other agent
sets it, so a move by `sorting` and a move by `invoices` stay told apart.
The keyword is asked for after the move in every stage. The runtime takes
nothing after a refused move and records only what follows a move recorded
only, by the stage or for a held group, so it never stands without the
move (decided 2026-11-18). Below `full` and for a held group the state
file holds it as recorded and not set. The name has no `$` in front, as IMAP registers
such keywords with meanings (`$Junk`, `$label1`), and it carries the
prefix `agent-` of the [agent contract](../agent-contract.md), which no mail
client or other tool is known to use. `MAILBOX_AGENTS_KEYWORD` names
another.

### By stage

| Stage | Folder creation | Move | Keyword |
|---|---|---|---|
| `shadow` | recorded | recorded | recorded |
| `keyword` | recorded | recorded | recorded. It goes with the move, so the stage acts like `shadow` |
| `full` | made | made, but for a held group | set, but for a held group |

Below `full` a folder recorded as to be made counts as there for the
folder and the move below it in the same effect, so both are recorded.

### What is stored

- The decision: the label is the name of the group or `none`, its source is
  `baseline`, its details say whether one group, none or two alike matched,
  the kind of rule, and whether the group is held. No quote and no sender
  is stored.
- No model step. The decision is stored under an empty model alias.
- **The version of the decision is the list (decided 2026-11-18).** It is
  `list-` and the first 12 hex digits of the SHA-256 of the list as read,
  in JSON with sorted keys. A changed list, a sender, a folder or `hold`,
  gives a new version, and a message taken up again, as by `backfill`, is
  decided anew under it. So the label, the details and `report` follow the
  list the message was acted on with, and a message decided `none` before
  a sender was added counts as moved once it is.
- The group is looked up again when the agent acts, against the list as it
  is then. So a sender added to the list reaches older mail through
  `backfill`.

## 4. The action `create_folder` (decided 2026-11-18)

Given a list, the agent may make the folders of the list itself.

| | |
|---|---|
| What | makes one folder that is missing. A folder below a missing one is made after it, each as an action of its own |
| Which | only a folder the agent was configured with: for `sorting` a folder of the list or one above it, for `invoices` the subfolder its pattern gives below a folder it looks in, and each folder between the two |
| Never | the trash, junk or spam, nor below them. Nor a folder that exists, under any case |
| When | in the stage `full`, right before the first move that needs it |
| Recorded | like every action: the path, the stage, whether it was made |
| Taken back | not by an agent: deleting a folder needs a right no agent has. An empty folder is removed by the owner |

It is the one action without a reverse of its own. It is accepted because
it changes no message.

How the runtime knows which folders an agent may make: the agent answers
for each path, with `may_create`, whether its configuration names it, and
the executor refuses any other. A method rather than a set of paths,
because `invoices` knows its subfolders only from the folder a message
lies in.

The [agent contract](../agent-contract.md), [safety](../safety.md) and
[mailbox service](../mailbox-service.md) describe the action, the folders
an agent declares, and folder creation in `sources/mailbox.py`.

## 5. The sender is not proof

From is not authenticated. An exact address is forged as easily as a
pattern: the kinds of rule differ in how much they cover, not in how far
they can be trusted. A folder named after a bank makes a forged mail look
genuine.

What would settle it is the result of the receiving server's check of the
sender (SPF, DKIM, DMARC), which the server writes into the message. The
mailbox service exposes no header of a message (measured 2026-11-17 against
0.7.5). The need was handed to that project on 2026-11-18.

Until then **a group can be held (decided 2026-11-18)**: `"hold": true`
records its moves as `shadow` does, whatever the stage of the agent, and
`report` shows them. It is meant for a group whose folder would lend trust.
Left out, a group is not held.

Once the service answers per message whether the sender's domain was
verified, a group gets a switch that moves verified mail only.

## 6. Settings

| Setting | Meaning |
|---|---|
| `MAILBOX_AGENTS_SORTING_FILE` | the list of section 2. Required |

The stage, the accounts and the rest are the settings of every agent
([configuration](../configuration.md)).

## 7. Which mail (decided 2026-11-18)

New mail as it arrives, and older mail only through `backfill --days N`, in
`shadow` first.

## 8. Report

- Per group: how many messages were moved, recorded, held, or not moved,
  when the move was refused.
- The senders in no group that wrote most often, as candidates for the
  list.
- The messages left alone because two groups matched.

## 9. Evaluation

`sorting` asks no model. Its rules are the whole decision, and the tests on
invented mail cover them. A gold set is optional. Where one is kept, its
label is the name of the group or `none`, in the existing gold format, and
the existing scoring serves.

## 10. Tests, all on invented mail

1. Each row of the table in section 3.
2. Each row of the stage table.
3. Address before pattern, two groups alike, case ignored.
4. A wrong list: each rule of section 2 broken once, a domain rule among
   them.
5. `create_folder`: a folder of the list is made, a folder outside it is
   refused, one below the trash is refused, a folder that exists is not
   made again, a nested folder is made from the top.
6. A sender added to the list reaches a message decided before.
7. No model call is made and no call is counted.
8. A held group in `full` moves nothing.

## 11. Measured first, on the live setup

Measured 2026-11-18, IMAP at Stalwart, service 0.7.5. The results stand in
[mailbox service](../mailbox-service.md).

1. A move made through the service reaches the change feed as
   `message.updated` of the same message, which keeps its id.
2. Creating a folder works at the top and below another.
3. A folder that exists in another case is not refused: the service makes
   a second one. The executor compares names ignoring case before it makes
   a folder.

## 12. Order of the build

Each step is one commit with the gates green and the specs it touches.

| Step | Content | Done when |
|---|---|---|
| S1 | The three measurements of section 11 | their results stand in [mailbox service](../mailbox-service.md) |
| S2 | `sources/mailbox.py`: creating a folder | offline tests against the fake service |
| S3 | Contract and executor: `create_folder`, the folders an agent declares | tests 5 of section 10, the tables of the contract spec |
| S4 | The list: reading, validating, matching, in `agents/sorting/` | tests 3 and 4. `invoices` keeps its own list until I5 |
| S5 | `agents/sorting/`: select, admit, baseline, decide without a model, effect | tests 1, 2, 6, 7, 8 |
| S6 | `report` for `sorting`, the setting, the example list | section 8 shown on invented mail |
| S7 | Live: `sorting` in `shadow` and in `full` on the test account | `live/sorting.py`, folders made, mail moved and put back. Not `live/smoke.py`, which writes nothing |
| S8 | [invoices](invoices.md) rebuilt, its own steps I1 to I6 | see there |

A run on the owner's account is the owner's decision, in `shadow` first.

## 13. What the revision dropped

- **Categories inside `sorting`, one agent that sorts and recognises
  invoices.** Two agents it is (decided 2026-11-18), for three reasons. An
  agent has one stage: a changed prompt puts it back into `shadow`, and
  with it the moves by sender that no model takes part in. A gateway that
  is away would hold back mail that needs no model. And a category is not
  configuration: it is a prompt, rules and a gold set, so a list cannot add
  one.
- **`invoices` and `sorting` side by side with a waiting time.** A message
  whose model call waits for a gateway that is away would be moved by
  `sorting` in the meantime, and `invoices` would then skip it.
- **A keyword per group.** The runtime lets an agent set one keyword, its
  own.
- **A gold item that names a folder.** The folder follows from the group
  and the list, and the gold format has no place for it.
- **One list for both agents.** `invoices` must work without `sorting`
  (decided 2026-11-18), so it takes folders, not groups.

## 14. Open

- The switch for verified senders, once the mailbox service can answer it.
