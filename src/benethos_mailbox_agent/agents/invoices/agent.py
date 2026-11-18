"""``invoices``: is this incoming message an invoice, and from which supplier?

The model answers whether a message in the inbox is an invoice, and for
one that is not, which near miss it is. The supplier comes from a sender
rule of the list when one matches, and the model cannot overrule it. When
none matches, the model may name a supplier of the list, with a quote the
code finds in the mail (decided 2026-11-17). An invoice gets the keyword,
and one of a known supplier is moved to that supplier's folder under the
parent. An unknown sender's invoice stays in the inbox, and ``report``
names the sender as a candidate for the list. See SPECS.md section 10.1.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from functools import cached_property

from ...contract import (
    Action,
    ActionRequest,
    Agent,
    Context,
    Limits,
    Requires,
    Route,
    Trigger,
)
from ...contract.prompts import load_prompt
from ...errors import ConfigError
from ...records import LABEL, Decision, Event, Evidence, MailMessage
from ...settings import PREFIX
from .baseline import baseline
from .schema import Answer, answer_schema, parts, render
from .suppliers import Kind, Supplier, Suppliers, load_suppliers

__all__ = ["Invoices"]


# The sender rules that move an invoice. From is not authenticated, so a
# domain rule and the model's choice mark only (decided 2026-11-17).
_MOVING_RULES = frozenset({Kind.ADDRESS, Kind.PATTERN})


def _mentions(supplier: Supplier, quote: str) -> bool:
    """Whether ``quote`` names ``supplier`` or one of its sender domains:
    what a quote must do to back the model's choice of a supplier."""
    said = " ".join(unicodedata.normalize("NFC", quote).split()).casefold()
    return any(name.casefold() in said for name in (supplier.name, *supplier.domains))


class Invoices(Agent):
    name = "invoices"
    version = "1"
    description = (
        "Marks invoices from suppliers, and moves those of a listed supplier "
        "into its folder."
    )
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset({Action.ADD_KEYWORD, Action.MOVE_TO_FOLDER})
    limits = Limits(model_calls_per_message=1, model_calls_per_day=2000)
    requires = Requires(settings=("invoices_folder", "invoices_suppliers_file"))
    default_keyword = "invoice"
    prompt_version = "v2"

    # -- what it reads besides its settings -----------------------------------

    def prepare(self) -> None:
        """Read the supplier list now, so a wrong one stops the start."""
        _ = self.suppliers

    @cached_property
    def suppliers(self) -> Suppliers:
        path = self.settings.invoices_suppliers_file
        if path is None:
            raise ConfigError(f"{PREFIX}INVOICES_SUPPLIERS_FILE is not set")
        return load_suppliers(path)

    @cached_property
    def system(self) -> str:
        names = ", ".join(f'"{name}"' for name in self.suppliers.names) or "(none)"
        return load_prompt(__package__ or "", "system", self.prompt_version).replace(
            "{suppliers}", names
        )

    @cached_property
    def schema(self) -> type[Answer]:
        return answer_schema(self.suppliers.names)

    @property
    def parent(self) -> str:
        return (self.settings.invoices_folder or "").strip("/")

    # -- the contract -------------------------------------------------------------

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE if event.type == "message.created" else None

    def admit(self, message: MailMessage) -> bool:
        return message.in_role("inbox")

    def baseline(self, message: MailMessage) -> Decision:
        return baseline(message, self.suppliers)

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        answer = await context.model.ask(
            system=self.system,
            content=render(message),
            evidence=parts(message),
            schema=self.schema,
        )
        label, quote, near_miss = answer.label, answer.quote, answer.near_miss
        evidence = [Evidence(field=LABEL, value=label, quote=quote)]
        fields: dict[str, str] = {}
        details: dict[str, str] = {}
        if label == "other" and near_miss != "none":
            fields["near_miss"] = near_miss
            evidence.append(Evidence(field="near_miss", value=near_miss, quote=quote))
        if label == "invoice":
            evidence += self._supplier(message, answer, fields, details)
        return Decision(
            label=label,
            source="model",
            fields=fields,
            evidence=tuple(evidence),
            details=details,
        )

    def _supplier(
        self,
        message: MailMessage,
        answer: Answer,
        fields: dict[str, str],
        details: dict[str, str],
    ) -> list[Evidence]:
        """The supplier of an invoice: a sender rule first, the model's
        choice from the list only when no rule matches."""
        sender = message.sender.email if message.sender else None
        named = answer.supplier
        rule = self.suppliers.match(sender)
        if rule is not None:
            fields["supplier"] = rule.supplier.name
            details["supplier_source"] = "rule"
            details["supplier_rule"] = rule.kind.name.lower()
            if named and named != rule.supplier.name:
                details["model_supplier"] = named
            return [
                Evidence(
                    field="supplier", value=rule.supplier.name, quote="", found=True
                )
            ]
        said = answer.supplier_quote
        chosen = self.suppliers.named(named) if named else None
        if chosen is not None and said and _mentions(chosen, said):
            fields["supplier"] = chosen.name
            details["supplier_source"] = "model"
            return [Evidence(field="supplier", value=chosen.name, quote=said)]
        details["supplier_source"] = "none"
        if named:
            details["model_supplier"] = named
        return []

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        if decision.label != "invoice":
            return []
        requests = [
            ActionRequest(
                Action.ADD_KEYWORD, message.ref, keyword=self.keyword, why="invoice"
            )
        ]
        # The rule is applied anew against the list as it is now, so a
        # supplier added since reaches an invoice decided before (decided
        # 2026-11-17). The decision keeps who chose at the time.
        sender = message.sender.email if message.sender else None
        rule = self.suppliers.match(sender)
        if rule is not None and rule.kind in _MOVING_RULES:
            requests.append(
                ActionRequest(
                    Action.MOVE_TO_FOLDER,
                    message.ref,
                    folder=f"{self.parent}/{rule.supplier.folder}",
                    why="supplier",
                )
            )
        return requests

    def summarize(self, decided: list[tuple[str | None, Decision]]) -> list[str]:
        """The senders of invoices no supplier of the list was found for,
        with how many each sent: candidates for the list."""
        counted = Counter(
            sender.lower()
            for sender, decision in decided
            if sender
            and decision.label == "invoice"
            and decision.actionable
            and "supplier" not in decision.fields
        )
        if not counted:
            return []
        return ["candidates for the supplier list:"] + [
            f"  {sender} ({count} invoice{'s' if count > 1 else ''})"
            for sender, count in counted.most_common()
        ]
