# The agent `sorting` (planned)

> **Status: planned on 2026-11-18, not built.** The name is a working name.
> Its purpose: the mail of providers such as a shop, a hoster or a bank
> goes into a folder of its own, and one folder may take several, such as
> all banks. It is a more general form of the invoice agent. What is
> decided is marked so, the rest is the proposal.

**Question:** a message from a known sender: which group does it belong to,
and does it fall into a category of that group, such as an invoice?

`sorting` is the general form of [invoices](invoices.md): groups of senders
with a folder each, and within a group categories with folders of their
own. `invoices` is one configuration of it, see the end of this file.

| | |
|---|---|
| Triggers | `message.created` in the inbox, and `backfill` for older mail |
| Baseline | the sender rules of the list, and for a category the rules of that category, such as those of `invoices` |
| Model | only for a group that has categories: the category of the message or none, with a quote. No model for a group without categories |
| Actions | `move_to_folder`, and `add_keyword` for a category that names one |

## Groups (decided 2026-11-18)

A list in a JSON file, `MAILBOX_AGENT_SORTING_FILE`, in the format of the
supplier list of `invoices`. Each entry is a group: a name, its folder and
the senders that belong to it. The folder is chosen freely: one folder for
several senders, such as all banks in `Bank`, or one per sender, or a
folder below another.

```json
{
  "groups": [
    {"name": "Bank", "folder": "Bank",
     "senders": ["*@traderepublic.com", "*@db.com"]},
    {"name": "Hosting", "folder": "Hosting",
     "senders": ["*@hosting.example"],
     "categories": {"invoice": "{folder}/Rechnungen"}}
  ]
}
```

The addresses above are examples, not checked. A sender rule is an
address, a pattern with `*` or a domain, as in `invoices`. The most
specific rule wins, and two groups whose rules of the same kind both match
leave the sender unmatched.

## Categories

A group may name categories, each with the folder its messages go to. The
folder is a pattern, `{folder}` the group's folder, `{name}` its name. The
first idea is the group's folder first and the category below it,
`{folder}/Rechnungen`, and it must be adjustable (2026-11-18). A message of
the group that falls into no category goes to the group's folder.

The first category is `invoice`, with the meaning `invoices` gives it in
prompt `v3`: an invoice, a notice that one is ready, a receipt that carries
its invoice and a credit note. Its prompt, schema, rules and evidence are
those of `invoices`, copied into the agent: an agent is self-contained. A
category whose quote is not found counts as none, and the message goes to
the group's folder.

## What moves (proposal)

- **Only an address or a pattern rule moves**, as in `invoices` and
  [safety](../safety.md). A domain rule marks the message with the group's
  keyword, if the group names one, and moves nothing.
- **Phishing.** A bank's folder makes a forged mail look trusted. The
  sender is not authenticated, and the mailbox service exposes neither the
  DKIM nor the SPF result **(to verify whether it can)**. Until it does, a
  group that names a bank should use exact addresses rather than patterns.
- **The agent creates no folder.** A move into a folder that does not exist
  is refused and logged, as in `invoices`.
- **Only from the inbox.** A message already in another folder is the
  owner's choice and stays.

## Which mail (decided 2026-11-18)

New mail as it arrives, and older mail only through `backfill --days N`, in
`shadow` first.

## Beside `invoices` (decided 2026-11-18)

Both agents stay for now. They must not both move the same message, so on
one account one of two holds:

- `sorting` has an `invoice` category: it takes the place of `invoices`,
  which does not run on that account.
- `sorting` has none: it leaves a message carrying the keyword of
  `invoices` alone, and takes a message up only some minutes after it
  arrived, so `invoices` goes first. The delay is a setting.

`invoices` as a configuration of `sorting`: one group per supplier with its
sender rules, the category `invoice` with the folder
`Rechnungen/{name}` and the keyword `invoice`, and no folder for a message
of the group that is no invoice, so it stays in the inbox. When `sorting`
scores as well as `invoices` on the same gold set and in `shadow` on the
owner's account, `invoices` can be retired.

## Evaluation

A gold item names the folder a message belongs in, or none. The report
counts each message right, in the wrong folder, moved though it should
stay, or left though it should move, per group, and the category beside it
as `invoices` scores its label.

## Open

- The name of the agent.
- The keyword of a group, if any, and whether a category sets one besides
  `invoice`.
- The delay beside `invoices`.
- Whether the mailbox service can expose the result of the sender's
  authentication, which a bank's folder would need.
