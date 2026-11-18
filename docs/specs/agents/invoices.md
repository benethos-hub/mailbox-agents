# The agent `invoices`

> **Status: version 4, rebuilt on 2026-11-18 after [sorting](sorting.md),
> steps I1 to I6 of the plan at the end, evaluated on the invented mail of
> the test account and run there in `shadow` beside `sorting`.
> Not run on a real mailbox in this version.**

**Question:** is this message an invoice?

| | |
|---|---|
| Triggers | `message.created` in the inbox or in a folder it looks in, and `message.updated` for a message with an open item |
| Baseline | a PDF or XML attachment, invoice words in subject and attachment names, phrases of a notice that an invoice waits at the supplier, near-miss words in the subject, a receipt that carries its invoice taken as one, and a credit note. The sender plays no part |
| Model | label `invoice` or `other`, for `other` the near miss it is: reminder, quotation, order confirmation, payment receipt, none. One quote |
| Actions | `add_keyword`, `move_to_folder`, and `create_folder` for the subfolder only |

**What counts (decided 2026-11-17).** An invoice is a message that carries
an invoice a supplier sent, or that tells one is ready to be fetched. The
second kind matters: many suppliers send a notice and no file. A receipt
that carries the invoice for its payment is an invoice too, whatever it
calls itself. Only a confirmation of a payment with no invoice is the near
miss `payment_receipt` (decided 2026-11-18: the owner's receipts of a
subscription carry the invoice, and prompt `v1` left them out). A credit
note (German `Gutschrift`) counts as an invoice too: it books like one with the
opposite sign (decided 2026-11-18 for now, prompt `v3`).

**The folder says whose invoice it is (decided 2026-11-18).** `invoices`
asks one question: is this message an invoice? It no longer asks from which
supplier. It moves an invoice into a subfolder of the folder it lies in.
Who put the message there does not matter: [sorting](sorting.md), a rule of
the mail server or the owner by hand. Filing by provider comes first, the
subfolder for invoices in a second run.

**It works without `sorting` (decided 2026-11-18).** So the folders it
looks in are a setting, and it knows nothing of groups or sender rules.

## Settings

| Setting | Meaning | Unset |
|---|---|---|
| `MAILBOX_AGENTS_INVOICES_FOLDERS` | the folders it looks in, separated by commas. `Parent/*` stands for every folder directly below `Parent`, `*` for every folder at the top without a role | the inbox alone |
| `MAILBOX_AGENTS_INVOICES_SUBFOLDER` | where an invoice goes, as a pattern that starts with `{folder}/`, the folder the message lies in, such as `{folder}/Rechnungen` | an invoice is marked and stays |
| `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` | a folder for an invoice found in the inbox. It must be there, it is not made | it is marked and stays in the inbox |

The inbox is always looked in. A folder is named by its path, case
counting. A message in a folder below a named one, such as the subfolder
itself, is not looked at, so an invoice is not asked about twice.

**`*` takes in the owner's own folders (decided 2026-11-18).** It covers
every folder at the top that has no role, the owner's own among them, so
the folders of [sorting](sorting.md) may lie at the top. The inbox, sent
mail, drafts, the trash, junk, the archive and a folder of all mail have a
role and are not taken in. A folder named by its path is looked in whatever
its role, but the trash, junk and spam. The runtime makes a subfolder only
below a folder that exists and that the agent looks in, judged with its
role, so `*` makes none below sent mail, drafts or the inbox.

`Parent/*` and `*` are matched against the path of the folder a message
lies in, not resolved once at the start, so a folder `sorting` makes later
is looked in at once. At the start the settings are checked: a wrong one
stops it. `status` looks up in the mailbox service the folders that should
be there, those named, the parents of `Parent/*` and the inbox folder, and
names each one missing in each account the settings name, or says the
folders were not checked when no account is named. A missing one does
not stop the start, as `sorting` may make it later.

`backfill` takes up the messages of the last days in the inbox and in every
folder it looks in, account by account, each folder by its id.

`MAILBOX_AGENTS_INVOICES_FOLDER` and `MAILBOX_AGENTS_INVOICES_SUPPLIERS_FILE`
are retired with the supplier list and its examples (step I5). A `.env`
that still names them starts, as an unknown setting is ignored.

## What happens to a message

| The message | What happens |
|---|---|
| lies in no folder it looks in | nothing, `skipped` |
| is no invoice | nothing |
| is an invoice in a folder it looks in | the keyword, and a move to the subfolder, made when missing, each folder of the path as an action of its own |
| is an invoice in a folder it looks in, no subfolder pattern set | the keyword. It stays |
| is an invoice in the inbox | the keyword and an open item, and it stays. With an inbox folder set, which must be there, the keyword and a move into that folder, and no open item |
| was marked in the inbox and now lies in a folder it looks in | a move to the subfolder, no model call. The open item closes as `filed` |
| was marked in the inbox and now lies in a folder it does not look in | nothing. The open item closes as `moved_elsewhere` |

Where the message lies is looked up again when the agent acts. In
`shadow` the keyword, the folders and the move are recorded, in `keyword`
the keyword is set and the rest recorded. The runtime moves a message at
most once for the agent, so an invoice the owner takes out of its
subfolder stays where the owner put it.

**An invoice in the inbox is marked only, unless the owner sets a folder
(decided 2026-11-18).** A forged invoice is the commonest bait, and a
folder the model fills on its own judgement would make one look checked.

**No answer of the model chooses a folder.** The schema holds a label, a
near miss and a quote, nothing else: an answer with another field is
refused. The folder follows from where the message lies and the settings.

The prompt is `prompts/system.v4.md`, version `v4`. It names no supplier.
The model is given the sender, the subject, the names and types of the
attachments and the first 6000 characters of the text.

Recognising an electronic invoice by its embedded data needs the attachment
read and is not part of this version.

## Beside `sorting`

Without an inbox folder, whichever agent comes first, the end is the same:

- `invoices` first: the message is marked in the inbox and gets an open
  item. `sorting` moves it. The move reaches `invoices` as an update of the
  message, it finds the open item, sees the message in a folder it looks in and
  moves it on.
- `sorting` first: `invoices` finds the message in the folder it looks in
  and moves it on after its decision.

With an inbox folder set, an invoice `invoices` takes up first goes into
that folder, and `sorting` leaves it there.

The open item and the look at an updated message are what
[awaiting reply](awaiting_reply.md) uses already. An open item of an
invoice has no deadline: its due date lies in the year 9999, and the agent
has no tick. Every update of a message is fetched and looked at, as for
`awaiting_reply`, and one without an open item ends there.

## What changed from version 3

| Part | Version 3 | Version 4 |
|---|---|---|
| Question | an invoice, and from which listed supplier | an invoice |
| Triggers | `message.created` | `message.created`, and `message.updated` for a message with an open item |
| `admit` | in the inbox | in the inbox or in a folder it looks in |
| Model answer | label, near miss, supplier, two quotes | label, near miss, one quote |
| Prompt | `v3`, names the suppliers | `v4`, names none |
| Baseline | uses the supplier list | the invoice rules alone |
| Where an invoice goes | the folder of its supplier under one parent, by a sender rule of the list | the subfolder of the folder it lies in |
| Actions | `add_keyword`, `move_to_folder` | the same and `create_folder`, for the subfolder only |
| `report` | senders of invoices without a supplier | senders of invoices marked and not moved, as candidates for a group of `sorting` |
| Evaluation | label, and the supplier by its source | label alone |

Version 3 decided the supplier by a sender rule of a list, and the model
could name one of the list with a quote that names it (decided 2026-11-17).
Only an address or a pattern rule moved. That list and its rules are now
the business of [sorting](sorting.md), which moves by the sender before
`invoices` asks its question.

The existing gold set still serves: its labels stay. The invented gold sets
dropped their supplier field. In a gold file that still names one, the
supplier counts as missing, as the agent no longer answers it: drop the
field. The agent version is 4, and it starts in `shadow`.

## Measured first

Measured 2026-11-18, IMAP at Stalwart, service 0.7.5. The results stand in
[mailbox service](../mailbox-service.md).

1. A message that arrives in a folder other than the inbox reaches the
   feed as `message.created`.
2. `backfill` can list the messages of a folder by its id, account by
   account, not by its path. It looks the id up first.

## Order of the build

Steps S1 to S7 of [sorting](sorting.md) came first: this version needed the
action `create_folder` and the measurements. Each step is one commit.

| Step | Content | Done when |
|---|---|---|
| I1 | The two measurements above | done 2026-11-18 |
| I2 | The three settings, checked at the start, `status` names a folder that is missing | done 2026-11-18 |
| I3 | `admit` by folder, the supplier taken out of the schema, the baseline and the decision, prompt `v4` | done 2026-11-18 |
| I4 | The open item and the look at an updated message | done 2026-11-18 |
| I5 | `report` and the evaluation without the supplier, the old settings and the supplier list removed | done 2026-11-18 |
| I6 | Evaluation of `v4` on the gold set, then `shadow` on the test account beside `sorting` | done 2026-11-18, below |

A run on the owner's account is the owner's decision, in `shadow` first.

## Measured, version 4

On the 11 invented messages of the test account, 2026-11-18, the reports
in `reports/invoices/`. Numbers on invented mail say that the agent works
as built, not how well it sorts real mail.

| Model | Right | Invoices found | Near miss invented | Tokens in per message |
|---|---|---|---|---|
| `mail-classifier` (Claude Haiku 5.5) | 11 of 11 | 3 of 3 | 1 | 1081 |
| `mail-classifier-gpu` (local) | 11 of 11 | 3 of 3 | 2 | 495 |
| the rules alone | 10 of 11 | 3 of 3, and one more | | |

`live/invoices.py` ran `invoices` in `shadow` with `Providers/*` and
`{folder}/Rechnungen` beside `sorting` in `full`, in both orders.
`invoices` first: it marked the three invoices in the inbox and opened an
item for each. Once `sorting` had moved two of them, their updates reached
`invoices` through the feed after about 23 seconds, and it recorded the
folders and the moves into `Rechnungen` with no further model call. The
third, of a held group, stayed in the inbox with its item open. `sorting`
first: `backfill` found the two in the folders of their groups, and
`invoices` recorded the same. The mail was put back.
