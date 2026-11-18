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
