"""The evidence check: whether a quote is in the text the model was given.

A label and every extracted field carry a quote. The code looks for the
quote in the parts of the mail the model was given, each part on its own:
sender, subject, attachment names, text. The frame the code writes around
them, such as ``Subject:``, is no part. Both sides are brought to Unicode
NFC and their whitespace made uniform: every run of spaces, tabs, line
breaks and non-breaking spaces counts as one space, and the ends are
trimmed. Nothing else is forgiven, not case and not a changed character. A
quote of fewer than eight characters besides whitespace counts as not
found, so ``e`` or a colon backs nothing. A field whose quote is not found is
dropped. A label whose quote is not found makes the decision ``refused``:
it is recorded and not acted on. See SPECS.md section 11.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from ..records import LABEL, Decision

__all__ = ["MIN_QUOTE", "check", "contains", "normalize"]

# The fewest characters besides whitespace a quote must have to be found.
MIN_QUOTE = 8

_SPACE = re.compile(r"\s+", flags=re.UNICODE)


def normalize(text: str) -> str:
    """``text`` in Unicode NFC, every run of whitespace one space, the ends
    trimmed."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def contains(content: str, quote: str) -> bool:
    """Whether ``quote`` is in ``content``. A quote shorter than
    :data:`MIN_QUOTE` characters besides whitespace is in nothing."""
    needle = normalize(quote)
    if len(needle.replace(" ", "")) < MIN_QUOTE:
        return False
    return needle in normalize(content)


def check(decision: Decision, parts: Sequence[str]) -> Decision:
    """``decision`` with every quote looked up in ``parts``, the parts of
    the mail the model was given, each on its own.

    Each evidence is marked ``found``. One that code already found by a
    rule stays found. A field whose quote is missing or
    not found is dropped. A decision whose label has no quote that is
    found is ``refused`` with the reason ``evidence``.
    """
    evidence = tuple(
        item.model_copy(
            update={
                "found": item.found is True
                or any(contains(part, item.quote) for part in parts)
            }
        )
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
