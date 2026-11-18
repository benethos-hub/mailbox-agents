# The agent `inquiries`

**Question:** is this a project inquiry, and what does it say?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | phrases of an inquiry, patterns for dates and rates, and the sender domains and phrases of `INQUIRIES_PATTERNS_FILE` (JSON, optional) taken from the gold set |
| Model | label `inquiry` or `other`, then the fields below |
| Actions | `add_keyword` |

The label comes first (built 2026-11-17, prompt `system.v1.md`): an
inquiry gets the keyword `inquiry`. The rules call a message an inquiry
when its sender's domain is known, when it carries two phrases of an
inquiry, or one together with a date or a rate.

Fields, each optional: role, start, end, duration, workload, location,
remote share, contract form, intermediary, end client, rate, required
skills, desired skills, deadline to apply.

Every field comes with a quote from the message ([safety](../safety.md)). What a
message does not say stays empty. The fields come in the same call as the
label (built 2026-11-17, prompt `system.v3.md`, version `v3` since
2026-11-18), each either null or a value with its quote, in the schema as
`role`, `start`, `end`, `duration`, `workload`, `location`,
`remote_share`, `contract_form`, `intermediary`, `end_client`, `rate`,
`required_skills`, `desired_skills` and `deadline`. A field is null as a
whole, not its value and quote each: the Claude API compiles a schema with
at most 16 parameters whose type is a union, and refused the 28 of `v2`.
A test holds every agent's schema to that limit.
A message labelled `other` keeps none. The evaluation counts each field
right, wrong, missing, invented or rightly empty.

Recognising an inquiry seen before, and anything that writes a reply, come
later ([roadmap](../roadmap.md)).
