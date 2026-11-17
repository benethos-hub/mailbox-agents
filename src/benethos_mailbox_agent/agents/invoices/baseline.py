"""The question of invoices answered by rules alone.

A near-miss word in the subject makes a message ``other`` with that near
miss. Otherwise an invoice word in the subject or an attachment name, a
phrase that says an invoice is ready, or a listed sender with a PDF or XML
attachment makes it an ``invoice``. The supplier comes from the list. The
evaluation sets these rules beside the model, so what the model adds is a
number. See SPECS.md section 10.1.
"""

from __future__ import annotations

from ...records import Decision, MailMessage
from .suppliers import Suppliers

__all__ = ["baseline"]

INVOICE_WORDS = ("rechnung", "invoice", "faktura", "facture")

READY_PHRASES = (
    "rechnung ist online",
    "rechnung steht",
    "zum abruf bereit",
    "rechnung verfügbar",
    "neue rechnung",
    "invoice is ready",
    "invoice is available",
    "invoice is now available",
    "new invoice",
)

NEAR_MISS_WORDS: dict[str, tuple[str, ...]] = {
    "reminder": ("zahlungserinnerung", "mahnung", "reminder", "overdue", "past due"),
    "quotation": ("angebot", "quotation", "kostenvoranschlag", "your quote"),
    "order_confirmation": (
        "bestellbestätigung",
        "auftragsbestätigung",
        "bestellung",
        "order confirmation",
        "your order",
    ),
    "payment_receipt": (
        "zahlungseingang",
        "zahlung erhalten",
        "payment received",
        "payment confirmation",
    ),
}

FILE_TYPES = ("application/pdf", "application/xml", "text/xml")


def baseline(message: MailMessage, suppliers: Suppliers) -> Decision:
    subject = (message.subject or "").lower()
    names = " ".join((a.filename or "").lower() for a in message.attachments)
    text = message.text[:2000].lower()
    for near_miss, words in NEAR_MISS_WORDS.items():
        if any(word in subject for word in words):
            return Decision(
                label="other", source="baseline", fields={"near_miss": near_miss}
            )
    sender = message.sender.email if message.sender else None
    rule = suppliers.match(sender)
    has_file = any(a.content_type in FILE_TYPES for a in message.attachments)
    invoice = (
        any(word in subject or word in names for word in INVOICE_WORDS)
        or any(phrase in subject or phrase in text for phrase in READY_PHRASES)
        or (rule is not None and has_file)
    )
    if not invoice:
        return Decision(label="other", source="baseline")
    if rule is None:
        return Decision(
            label="invoice", source="baseline", details={"supplier_source": "none"}
        )
    return Decision(
        label="invoice",
        source="baseline",
        fields={"supplier": rule.supplier.name},
        details={"supplier_source": "rule", "supplier_rule": rule.kind.name.lower()},
    )
