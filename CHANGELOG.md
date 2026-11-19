# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

Every user-facing change gets an entry under `[Unreleased]` in the same
commit that makes the change. Design decisions live in
[SPECS.md](SPECS.md).

## [Unreleased]

### Added

- The console script `benethos-mailbox-agents` with the commands `worker`,
  `run`, `backfill`, `status` and `paths`, and `--env-file`.
- The command `report`: what an agent decided and did, or in `shadow` would
  have done, with subject and sender fetched at the moment of the report.
- The command `eval`: an agent over a gold set of labelled mail, the model
  beside the rules, precision and recall per label, each field right,
  wrong, missing or invented, and a report file of numbers only.
- The command `health`, and metrics in the Prometheus text format on
  `MAILBOX_AGENTS_METRICS_PORT` while `worker` runs.
- The container image, one for all agents, and compose files for
  operation, one service per agent behind a profile of its name, and for
  development against a test account of invented mail.
- The agent `invoices`: marks invoices and invoice notices from suppliers
  with the keyword `agent-invoice`, in the inbox and in the folders
  `MAILBOX_AGENTS_INVOICES_FOLDERS` names, and moves one into the subfolder
  `MAILBOX_AGENTS_INVOICES_SUBFOLDER` names below the folder it lies in.
- The agent `awaiting_reply`: opens an item for each sent message the
  model finds asking for an answer, closes it on a reply in its thread or
  when the keyword is taken off, and sets the keyword `agent-awaiting-reply` on
  the sent message after `MAILBOX_AGENTS_REPLY_DAYS` working days.
- The agent `inquiries`: marks project inquiries with the keyword
  `agent-inquiry` and records what an inquiry says, role, start, end, duration,
  workload, location, remote share, contract form, intermediary, end
  client, rate, skills and deadline, each with a quote from the mail. Its rules read phrases, dates and rates, and the sender
  domains and phrases of `MAILBOX_AGENTS_INQUIRIES_PATTERNS_FILE`.
- The agent `counting`, which counts what arrives and is sent and changes
  nothing, for checking a deployment end to end.
- The setting `MAILBOX_AGENTS_GATEWAY_ALLOW_HTTP`, for a gateway reached
  over http between two containers.
- The log line of an action names why the agent asked for it, as a short
  code such as `due` or `invoice` after a colon.
- `docs/LOGGING.md`: the levels, the shape of a line, what never goes
  into one, and the catalogue of every line the agents write.
- The agent `sorting`: moves mail of listed senders from the inbox into
  the folder of their group, makes a missing folder first, and sets the
  keyword `agent-sorted` with the move. No model. The groups are a JSON
  file in `MAILBOX_AGENTS_SORTING_FILE`. A sender rule is an address, a
  pattern of one domain or `*@*.domain` for its subdomains, and a group
  with `"hold": true` has its moves recorded only.
- The action `create_folder`: the runtime makes a folder an agent's
  configuration names, below one that exists, never below the trash, junk
  or spam.

### Changed

- An agent does not start when `MAILBOX_AGENTS_KEYWORD` is the keyword of
  another agent, and `status` warns when the setting is set at all: in
  settings several agents share, it gave them one keyword, and
  `invoices` skipped what `sorting` had marked.
- `MAILBOX_AGENTS_KEYWORD` takes lower case letters, digits and dashes
  only, as the agents' own keywords. A keyword such as `$Junk`, which
  would make every marked mail spam, or one with capitals or control
  characters stops the start.
- The sender's name and the subject a model is given are cut at 300
  characters, and `invoices` lists at most 20 attachments within 1000
  characters, so a mail cannot blow up a model call. Mail below these
  limits reaches the model as before, under the same prompt versions.
- The project is named `benethos-mailbox-agents`, in the plural, as it
  holds several agents: the distribution, the console script, the import
  package `benethos_mailbox_agents`, the container image, the settings
  prefix `MAILBOX_AGENTS_` and the metrics `mailbox_agents_*`.
- Every agent's keyword has the form `agent-<word>`: `agent-invoice`,
  `agent-awaiting-reply`, `agent-inquiry`, `agent-sorted`. A mail marked
  with an older keyword keeps it. `MAILBOX_AGENTS_KEYWORD` still names
  another.
- The agent `invoices` is version 4 with the prompt `v4`. It asks only
  whether a message is an invoice, no longer from which supplier. It looks
  in the inbox and in the folders `MAILBOX_AGENTS_INVOICES_FOLDERS` names,
  with `Parent/*` for the folders below one and `*` for every folder at the
  top without a role, and moves an invoice into the subfolder
  `MAILBOX_AGENTS_INVOICES_SUBFOLDER` names below the folder it lies in,
  such as `{folder}/Rechnungen`, made when missing, and marks it only when
  that setting is unset. An invoice in the inbox is
  marked and stays, unless `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` names a
  folder. The rules no longer take a listed sender with a file for an
  invoice. `status` names a folder an agent expects that is missing.
- The agent `invoices` is version 5, the prompt stays `v4`. The folder
  `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` names is an end station: where
  `MAILBOX_AGENTS_INVOICES_FOLDERS` takes it in, an invoice put there by
  `sorting` or by hand is marked and stays, and nothing is made below it.
  Before, that folder was never looked in, and such an invoice was neither
  marked nor filed.
- `invoices` skips a message that carries its keyword and that its state
  file does not know, before the rules and the model: after a state file
  made anew, a filed invoice taken out of its subfolder is neither asked
  about nor moved again. Taking the keyword off has such a message looked
  at again. `backfill` still reaches the marked messages the state file
  knows.
- `status` lists for `invoices`, per account, the folders that matter: the
  inbox and each folder it looks in with where an invoice there goes, the
  inbox folder, and each subfolder, which it does not look in.
- `backfill` takes up the messages of the folders an agent looks in besides
  the inbox and sent mail, for `invoices` those it looks in.
- An agent moves a message at most once. A message its owner moved back,
  into the inbox or anywhere, stays there, also when `backfill`
  takes it up anew. After a refused move the rest of the message's
  actions are not taken.
- The specification is split: `SPECS.md` is its table of contents, with
  the decisions that matter most, and the details are in `docs/specs/`,
  one file per topic and one per agent. It plans the agent `sorting`,
  which moves mail of known senders into folders of free groups.
- The agent `invoices` asks with the prompt version `v3`: a receipt that
  carries the invoice for its payment is an invoice, whatever it calls
  itself, and so is a credit note. Only a payment confirmation without an
  invoice is a `payment_receipt`. Every message is taken up anew with the
  new version.
- The rules of `invoices`, which the evaluation sets beside the model,
  know more notices that an invoice waits at the supplier, such as
  "Rechnung ist da", "Rechnung wurde bereitgestellt" or "your bill is
  ready", credit notes, and receipts: a receipt or "Quittung" is the near
  miss `payment_receipt`, unless it carries its invoice. The agent's
  version is 3, so the rules run anew for every message.
- The agent `inquiries` asks with the prompt version `v3`: a field the
  mail does not fill is null as a whole, not its value and its quote each.
  The Claude API refused the schema of `v2`, so `inquiries` runs on Claude
  now. Every inquiry is taken up anew with the new version.
- Every log line is one sentence in the past tense, such as
  `invoices set message m1 to done`, instead of key-value pairs. It
  starts with the time in ISO 8601 with milliseconds and the offset, the
  level and the source `benethos_mailbox_agents.activity.<area>.<name>`,
  which a level of its own can silence. On a terminal the line is in
  colour unless `NO_COLOR` is set. A library writes at `WARNING` and
  above only, through the same redaction.
- The runtime leaves a message in the trash, junk or spam alone, and moves
  no message into a folder below the trash, junk or spam.
- The evidence check looks for a quote only in the parts of the mail, not
  in the frame around them, brings both sides to Unicode NFC, and finds no
  quote of fewer than eight letters and digits. It compares word for word:
  case, punctuation, typographic quotes and dashes do not count, and a
  quote that starts with `Subject:` or another word of the frame is looked
  up without it. A changed or missing word still makes a quote not found.
- `report` writes a control character or line separator from a mail or a
  model as its escape, so a subject cannot move the cursor or fake a line.
- The gateway is reached over https, or over http to this machine. http to
  another machine needs `MAILBOX_AGENTS_GATEWAY_ALLOW_HTTP`.
- A second writer of a state file, such as `run` beside a running
  `worker`, is refused with a message naming the agent.
- The state file and the secrets of the live setup are written readable
  by their owner only.
- An action recorded and not carried out is recorded once per message and
  stage. A second `backfill` in `shadow` adds no row to the state file and
  no line to `report`.
- `sorting` decides a message anew under a changed list. Its decision is
  stored under a version made from the list, so after `backfill` the
  label, the details and `report` follow the list the message was moved
  with, not the one it was first decided with.
- `sorting` refuses a list that could never work: two groups that write a
  folder in two cases, such as `Bank` beside `bank/Sub`, a group named
  `none`, and a sender rule whose domain has an empty name, such as
  `*@shop..example` or `a@b.example.`.
- After a move or a folder recorded only, by the stage or for a held
  group, the runtime records the rest of the message's actions only too.
  `sorting` asks for its keyword in every stage, so in `shadow` and
  `keyword` and for a held group the state file and `report` show the
  keyword as recorded and not set.
- `status` names a folder an agent expects whose name is there in another
  case only as `folder in another case in <account>: <path>`, no longer as
  missing: the runtime neither moves into it nor makes it. It prepares
  each agent once, so it reads the `sorting` list once.
- `status` without `MAILBOX_AGENTS_ACCOUNTS` checks the folders an agent
  expects in every account its user is granted, as the worker takes them,
  instead of saying that no account is named.
- The baseline is stored per agent version and prompt version. After a
  changed `sorting` list, `report` shows the baseline of the new list
  beside the decision, not that of the list before. A state file of an
  earlier build runs the rules once more for a message taken up again.

### Removed

- The supplier list of `invoices`, its examples and the settings
  `MAILBOX_AGENTS_INVOICES_FOLDER` and
  `MAILBOX_AGENTS_INVOICES_SUPPLIERS_FILE`: the agent `sorting` files mail
  by its sender now, and `invoices` moves an invoice within the folder it
  lies in. A `.env` that still names them starts and ignores them.
- `report` for `invoices` no longer names candidates for the supplier
  list. It names the senders of invoices it marked and did not move.

### Fixed

- An evaluation report names only the labels and fields an agent declares
  as its own. Any other, such as the name of a group of `sorting`, becomes
  `label-<n>` or `field-<n>`, since a report is versioned.
- A gateway answer whose token counts are garbled, not numbers or below
  zero, counts no tokens. It ended the worker before, after the paid call
  and before the step was stored, so the same message was asked again
  after each restart, outside the daily limit.
- The evidence check matches whole words only, as specified: a quote
  whose first or last word is cut short, such as `voice number 1234` for
  `invoice number 12345`, is not found.
- `health` says what it measures: `last progress 42s ago` and
  `no progress yet`, not the last pass, since the loop's progress is
  written after each message and while it waits as well.
- An open item of `awaiting_reply` whose sent message was deleted closes
  as `message_gone` on the tick, instead of staying due and asking for
  its keyword every round.
- A write the mailbox service refuses, such as a keyword the provider
  does not take, and a message an agent reads for its actions that was
  deleted since, no longer stop the agent before its cursor. The refusal
  is logged and the next messages are taken up.
- A worker that waits long for its gateway or mailbox service stays
  healthy: it waits in slices of one poll interval and writes its progress
  after each.
- A gateway that is away holds up only the messages that need it: the
  others are taken up, and the tick marks what is due, unless a message
  still due waits for another reason.
- `health` answers 1 for an agent without a state file yet, not 2, which
  Docker keeps for itself.
- `run` answers 1 whenever the pass found the mailbox service or the
  gateway away, also with a backoff ceiling below the poll interval.
- `awaiting_reply` counts its keyword as set only once it is on the
  message. In `shadow` a star on a sent message no longer closes its item,
  an item is recorded once per stage, a refused keyword is offered again,
  and after `shadow` the stage `keyword` sets it. The state file gets
  migration 2.
- `awaiting_reply` opens no item for a sent message whose thread already
  holds a later answer, as after a backfill that took up the reply first.
- `backfill` no longer opens an `awaiting_reply` item again that a
  reply or a person closed.
- Keywords are compared without case, since the mailbox service may
  answer them in lower case. A `MAILBOX_AGENTS_KEYWORD` with capitals no
  longer closes every `awaiting_reply` item at once.
- `status` says `last progress:` instead of `last pass:`, since the time
  is the loop's last sign of progress, not its last complete pass.
- The commands that open a state file to write log when they made it or
  brought its schema forward.
- A message in a folder below the trash, junk or spam, such as
  `Trash/Old`, is left alone like one in the folder itself: no agent
  moves it or sets a keyword on it.
- The log line of an action of `sorting` ends in the code `group`, or
  `held` for a held group, instead of the group's name, which may name a
  person. A wrong sorting list names a wrong rule by its group and its
  place, such as `group 'Bank', sender 2`, no longer by the rule itself.
- The live checks in `live/` read their settings from their file alone. A
  `MAILBOX_AGENTS_` variable exported in the shell no longer points them
  at another account, a mailbox service not on this machine stops them
  with exit code 2, and each prints its account before it starts.
- A log line and `report` write a mark that sets the direction of text,
  such as U+202E, as its escape, so a sender's name or a subject can no
  longer turn the text after it around.
- The pre-commit hook in `.githooks/` finds a credential whatever the
  case of its name, such as `"password": "..."` in JSON or `token: ...` in
  YAML, and refuses every file in a folder `secrets/`, also one added with
  `git add -f`.
- `backfill` ends with exit code 1 when the gateway is away, after asking
  it once, instead of asking it again and again without end. The live
  checks stop the same way.
- `invoices` files an invoice marked in the inbox and moved later also
  when the mailbox service was away while it made the subfolder or moved
  the message: the same update on the next pass files it, where it was
  dropped before.
- `invoices` no longer looks in its subfolder or its inbox folder when
  `MAILBOX_AGENTS_INVOICES_FOLDERS` would take them in, as
  `Invoices,Invoices/*` takes in `Invoices/Rechnungen`. A `backfill` made
  an empty `Rechnungen` below the filed invoice before.
- No folder is made for the move of a message the agent moved before.
  The move is refused as before, and the folder the owner deleted after
  moving the message back is no longer made again, empty.
- A move into a folder held and not made, and a folder below one, are
  recorded only, also in `full`. The move was sent with an empty folder
  and recorded as carried out, which then refused every later move of
  the message.
- A move the mailbox service carried out without its answer reaching the
  agent, after a timeout, counts as the agent's move. A later `backfill`
  no longer moves a message again that the owner moved back.
- `invoices` opens an item for an invoice in the inbox also when
  `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` is set. When that folder is
  missing or the stage is below `full`, an invoice `sorting` moves later
  is filed into its subfolder, where it stayed unfiled before.
- `backfill` without `MAILBOX_AGENTS_ACCOUNTS` looks in the folders of
  every account the agent's user is granted. An account whose inbox and
  sent mail were empty, as `sorting` leaves one, was left out before.
- A folder the owner deleted or renamed while the worker runs is made
  again for the next move into it. The worker took it as there until it
  was restarted, and each move into it failed.
- A move into a folder deleted in the moment before it, and a folder made
  below one, are refused and logged as refused. The message was ended as
  `skipped`, as if it had been deleted.
- An agent acts on where a message lies after its model answered. With
  `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` set, an invoice `sorting` moved
  while the model was asked was moved on into the inbox folder, out of the
  folder of its group. It is now filed into the subfolder there.
- The open item of an invoice deleted after it was marked in the inbox
  closes as `message_gone` on its next update. It stayed open before, and
  the state file kept it.
