"""The evidence check: whether a quote is in the text the model was given.

A label and every extracted field carry a quote. The code looks for the
quote in the content of the call, with whitespace made uniform on both
sides: every run of spaces, tabs, line breaks and non-breaking spaces
counts as one space, and the ends are trimmed. Nothing else is forgiven,
not case and not a changed character. A field whose quote is not found is
dropped. A label whose quote is not found makes the decision ``refused``:
it is recorded and not acted on. See SPECS.md section 11.
"""

from __future__ import annotations

import re

from ..records import LABEL, Decision

__all__ = ["check", "contains", "normalize"]

_SPACE = re.compile(r"\s+", flags=re.UNICODE)


def normalize(text: str) -> str:
    """``text`` with every run of whitespace one space, the ends trimmed."""
    return _SPACE.sub(" ", text).strip()


def contains(content: str, quote: str) -> bool:
    """Whether ``quote`` is in ``content``. An empty quote is in nothing."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(content)


def check(decision: Decision, content: str) -> Decision:
    """``decision`` with every quote looked up in ``content``.

    Each evidence is marked ``found``. A field whose quote is missing or
    not found is dropped. A decision whose label has no quote that is
    found is ``refused`` with the reason ``evidence``.
    """
    evidence = tuple(
        item.model_copy(update={"found": contains(content, item.quote)})
        for item in decision.evidence
    )
    backed = {item.field for item in evidence if item.found}
    fields = {name: value for name, value in decision.fields.items() if name in backed}
    refused = decision.refused
    if refused is None and LABEL not in backed:
        refused = "evidence"
    return decision.model_copy(
        update={"evidence": evidence, "fields": fields, "refused": refused}
    )
