"""The question of invoices answered by rules alone.

A near-miss word in the subject makes a message ``other`` with that near
miss, except a receipt that carries its invoice: a PDF or XML attachment,
and an invoice word in its name or in the text. Otherwise an invoice word
in the subject or an attachment name, a phrase that says an invoice is
ready, or a listed sender with a PDF or XML attachment makes it an
``invoice``. The supplier comes from the list. The
evaluation sets these rules beside the model, so what the model adds is a
number. See SPECS.md section 10.1.
"""

from __future__ import annotations

from ...records import Decision, MailMessage
from .suppliers import Suppliers

__all__ = ["baseline"]

# A credit note books like an invoice with the opposite sign (decided
# 2026-11-18).
INVOICE_WORDS = (
    "rechnung",
    "invoice",
    "faktura",
    "facture",
    "gutschrift",
    "credit note",
)

# A notice that an invoice waits at the supplier, in the subject or the
# text: many suppliers send no file.
READY_PHRASES = (
    "rechnung ist online",
    "rechnung ist da",
    "rechnung ist verfügbar",
    "rechnung steht",
    "rechnung verfügbar",
    "rechnung bereitgestellt",
    "rechnung wurde bereitgestellt",
    "rechnung wurde erstellt",
    "rechnung zum download",
    "rechnung herunterladen",
    "rechnung im kundencenter",
    "rechnung im kundenportal",
    "online-rechnung",
    "monatsrechnung",
    "zum abruf bereit",
    "neue rechnung",
    "invoice is ready",
    "invoice is available",
    "invoice is now available",
    "invoice has been issued",
    "new invoice",
    "bill is ready",
    "bill is available",
    "new bill",
    "statement is ready",
    "statement is available",
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
        "zahlungsbestätigung",
        "zahlungsbeleg",
        "quittung",
        "payment received",
        "payment confirmation",
        "receipt",
    ),
}

FILE_TYPES = ("application/pdf", "application/xml", "text/xml")


def baseline(message: MailMessage, suppliers: Suppliers) -> Decision:
    subject = (message.subject or "").lower()
    names = " ".join((a.filename or "").lower() for a in message.attachments)
    text = message.text[:2000].lower()
    has_file = any(a.content_type in FILE_TYPES for a in message.attachments)
    carries_invoice = has_file and any(
        word in names or word in text for word in INVOICE_WORDS
    )
    for near_miss, words in NEAR_MISS_WORDS.items():
        if near_miss == "payment_receipt" and carries_invoice:
            continue
        if any(word in subject for word in words):
            return Decision(
                label="other", source="baseline", fields={"near_miss": near_miss}
            )
    sender = message.sender.email if message.sender else None
    rule = suppliers.match(sender)
    invoice = (
        carries_invoice
        or any(word in subject or word in names for word in INVOICE_WORDS)
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
