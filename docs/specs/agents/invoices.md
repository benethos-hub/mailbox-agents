# The agent `invoices`

**Question:** is this incoming message an invoice, and is its sender a
supplier with a folder of its own?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | a sender on the supplier list, a PDF or XML attachment, invoice words in subject and attachment names, phrases of a notice that an invoice waits at the supplier, near-miss words in the subject, a receipt that carries its invoice taken as one, and a credit note (agent version 3, 2026-11-18) |
| Model | label `invoice` or `other`, for `other` the near miss it is: reminder, quotation, order confirmation, payment receipt, none, and for an invoice a supplier of the list or none |
| Supplier | a sender rule of the list first, the model's choice from the list only when no rule matches (decided 2026-11-17) |
| Actions | `add_keyword`, `move_to_folder` |

**What counts (decided 2026-11-17).** An invoice is a message that carries
an invoice a supplier sent, or that tells one is ready to be fetched. The
second kind matters: many suppliers send a notice and no file. A receipt
that carries the invoice for its payment is an invoice too, whatever it
calls itself. Only a confirmation of a payment with no invoice is the near
miss `payment_receipt` (decided 2026-11-18: the owner's receipts of a
subscription carry the invoice, and prompt `v1` left them out). A credit
note, a "Gutschrift", counts as an invoice too: it books like one with the
opposite sign (decided 2026-11-18 for now, prompt `v3`).

**One folder per supplier, under one parent (decided 2026-11-17).** The
parent is named in `MAILBOX_AGENT_INVOICES_FOLDER`. The supplier list is a
file named in `MAILBOX_AGENT_INVOICES_SUPPLIERS_FILE`. It is not versioned,
an example of it is. An entry names a supplier, the sender addresses or
domains it writes from, and its folder under the parent. Every folder must
exist. The agent creates none.

The list is JSON (decided 2026-11-17), read by the file's suffix so another
format is one reader more. `suppliers.example.json` shows it:

```json
{"suppliers": [
  {"name": "CloudHost", "folder": "CloudHost",
   "senders": ["billing@cloudhost.example", "cloudhost.example"]},
  {"name": "Telco", "folder": "Telco",
   "senders": ["rechnung@telco.example", "mailbox*@telco.example"]}
]}
```

A sender is an address, a pattern with `*` for a part that changes, or a
domain, which covers its subdomains too. Case is ignored. The most specific
rule wins: an address before a pattern before a domain. Two suppliers whose
rules of the same kind both match leave the sender unmatched. Names and
folders are unique, a sender rule belongs to one supplier, and a folder is
names between `/`, none empty, `.` or `..`. A wrong list stops the agent at
its start and `status` names what is wrong.

From is not authenticated, and a domain rule covers every address and
subdomain of it. So only an address or a pattern rule moves an invoice
into a supplier's folder. A domain rule and the model's choice mark only
(decided 2026-11-17).

The sender rule is applied again when the agent acts, against the list
as it is then. A supplier added to the list reaches an invoice decided
before once `backfill --again` takes it up, without a new model call.
The decision keeps who chose the supplier at the time (decided
2026-11-17).

| The message is | What happens |
|---|---|
| an invoice from a listed supplier, by an address or pattern rule | the keyword, and in stage `full` a move to the supplier's folder |
| an invoice from a listed supplier, by a domain rule or the model's choice | the keyword. It stays in the inbox |
| an invoice from a sender not listed | the keyword. It stays in the inbox, and `report` names the sender as a candidate for the list |
| not an invoice | nothing |

**The supplier (decided 2026-11-17).** When a sender rule of the list
matches, it decides the supplier and the model cannot overrule it: what the
model named instead is recorded as `model_supplier` and not used. When no
rule matches, the model may name a supplier of the list, as an enum in the
schema, with a quote that the code finds in the mail and that names the
supplier or a domain of its sender rules, case aside (decided
2026-11-17). Without that quote the supplier is dropped, its name kept as
`model_supplier`, and the invoice gets the keyword only. The
decision records the source of its supplier as `supplier_source`: `rule`,
`model` or `none`, and `report` and the evaluation tell them apart. So the
content of a mail can at worst give an invoice of an unlisted sender the
name of a listed supplier. It moves nothing, since only an address or a
pattern rule moves.

The prompt is `prompts/system.v3.md`, version `v3`. The model is given the
sender, the subject, the names and types of the attachments and the first
6000 characters of the text.

Recognising an electronic invoice by its embedded data needs the attachment
read and is not part of the first version.

## Planned: `invoices` after `sorting`

> **Decided in direction on 2026-11-18, not built.** Everything above
> describes the agent as it is built. What is decided below is marked so,
> the rest is the proposal.

`invoices` keeps one question: is this message an invoice? It no longer
asks from which supplier. It moves an invoice into a subfolder of the
folder it lies in, so the folder says whose invoice it is. Who put the
message there does not matter: [sorting](sorting.md), a rule of the mail
server or the owner by hand.

**It works without `sorting` (decided 2026-11-18).** So the folders it
looks in are a setting, read at its start, and it knows nothing of groups
or sender rules.

### Settings

| Setting | Meaning | Unset |
|---|---|---|
| `MAILBOX_AGENT_INVOICES_FOLDERS` | the folders it looks in, separated by commas. `Parent/*` stands for every folder directly below `Parent` | the inbox alone |
| `MAILBOX_AGENT_INVOICES_SUBFOLDER` | where an invoice goes, as a pattern. `{folder}` is the folder the message lies in, such as `{folder}/Rechnungen` | an invoice is marked and stays |
| `MAILBOX_AGENT_INVOICES_INBOX_FOLDER` | a folder for an invoice found in the inbox | it is marked and stays in the inbox |

The inbox is always looked in. A folder is named by its path. A message in
a folder below a named one, such as the subfolder itself, is not looked at,
so an invoice is not asked about twice.

`MAILBOX_AGENT_INVOICES_FOLDER` and `MAILBOX_AGENT_INVOICES_SUPPLIERS_FILE`
retire, with the supplier list and its example.

### What happens to a message

| The message | What happens |
|---|---|
| lies in no folder it looks in | nothing, `skipped` |
| is no invoice | nothing |
| is an invoice in a named folder | the keyword, and a move to the subfolder, made when missing |
| is an invoice in a named folder, no subfolder pattern set | the keyword. It stays |
| is an invoice in the inbox | the keyword and an open item. It stays, unless an inbox folder is set |
| was marked in the inbox and now lies in a named folder | a move to the subfolder, no model call. The open item closes |

**An invoice in the inbox is marked only, unless the owner sets a folder
(proposal, the owner has not answered).** A forged invoice is the commonest
bait, and a folder the model fills on its own judgement would make one look
checked. `report` names the senders of such invoices, as today.

### Beside `sorting`

Whichever agent comes first, the end is the same:

- `invoices` first: the message is marked in the inbox and gets an open
  item. `sorting` moves it. The move reaches `invoices` as an update of the
  message, it finds the open item, sees the message in a named folder and
  moves it on.
- `sorting` first: `invoices` finds the message in the named folder and
  moves it on after its decision.

The open item and the look at an updated message are what
[awaiting reply](awaiting_reply.md) uses already. An open item of an
invoice has no deadline.

### What changes in the agent

| Part | Today | Planned |
|---|---|---|
| Triggers | `message.created` | `message.created`, and `message.updated` for a message with an open item |
| `admit` | in the inbox | in the inbox or in a named folder |
| Model answer | label, near miss, supplier, two quotes | label, near miss, one quote |
| Prompt | `v3`, names the suppliers | `v4`, names none |
| Baseline | uses the supplier list | the invoice rules alone |
| Actions | `add_keyword`, `move_to_folder` | the same and `create_folder`, for the subfolder only |
| `report` | senders of invoices without a supplier | senders of invoices marked in the inbox |
| Evaluation | label, and the supplier by its source | label alone |

The gold set there is serves: its labels stay, its supplier field is no
longer scored. The agent version becomes 4, and it starts in `shadow`.

### To measure first

1. Whether the change feed names a message that arrives in a folder other
   than the inbox, such as one the mail server filed by a rule of its own.
2. Whether `backfill` can list the messages of a folder by its path. Today
   it lists by the role of a folder.

### Order of the build

Steps S1 to S7 of [sorting](sorting.md) come first: this plan needs the
action `create_folder` and the measurements. Each step is one commit.

| Step | Content | Done when |
|---|---|---|
| I1 | The two measurements above | their results stand in [mailbox service](../mailbox-service.md) |
| I2 | The three settings, the folders resolved at the start, `status` names a folder that is missing | tests of the settings and of `Parent/*` |
| I3 | `admit` by folder, the supplier taken out of schema, baseline and decision, prompt `v4` | each row of the table above but the last, on invented mail |
| I4 | The open item and the look at an updated message | the last row, in both orders with `sorting` |
| I5 | `report` and the evaluation without the supplier, the old settings and the supplier list removed | the suite green, the changelog names what was removed |
| I6 | Evaluation of `v4` on the gold set, then `shadow` on the test account beside `sorting` | a report under `reports/invoices/` |

A run on the owner's account is the owner's decision, in `shadow` first.
