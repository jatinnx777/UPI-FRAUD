"""Stage 3 - UPI payment URI parsing and validation.

Parses `upi://pay?...` URIs into structured fields and records any format
problems as issues. Missing optional fields are reported as notes, not errors.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

# Generic VPA shape: <handle>@<provider>. We deliberately do NOT require the
# provider to be on a list of known PSPs - an unfamiliar handle is not evidence of fraud.
VPA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,255}@[A-Za-z][A-Za-z0-9]{1,63}$")
AMOUNT_RE = re.compile(r"^\d{1,10}(\.\d{1,2})?$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

# Parameters defined by the UPI linking specification.
KNOWN_PARAMS = {
    "pa", "pn", "am", "cu", "tn", "mc", "tr", "tid", "url", "mam", "mode",
    "purpose", "orgid", "sign", "mid", "msid", "mtid", "ver", "qrmedium",
    "invoiceno", "invoicedate", "gstin", "gstbrkup", "category", "query",
}


@dataclass
class Issue:
    field: str
    code: str
    message: str


@dataclass
class ParsedPayment:
    is_upi: bool
    scheme: str = ""
    action: str = ""
    payee_vpa: str | None = None
    payee_name: str | None = None
    amount: str | None = None
    currency: str | None = None
    note: str | None = None
    merchant_code: str | None = None
    extra_params: dict[str, str] = field(default_factory=dict)
    unknown_params: list[str] = field(default_factory=list)
    duplicate_params: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "payee_vpa": self.payee_vpa,
            "payee_name": self.payee_name,
            "amount": self.amount,
            "currency": self.currency,
            "note": self.note,
            "merchant_code": self.merchant_code,
            "extra_params": self.extra_params,
        }


def _clean(value: str | None, max_len: int = 200) -> str | None:
    if value is None:
        return None
    value = value.strip()
    # Strip control characters so decoded text is safe to display.
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:max_len] if value else None


def parse_upi_uri(payload: str) -> ParsedPayment:
    text = payload.strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return ParsedPayment(is_upi=False, issues=[Issue("uri", "malformed_uri", "The QR content is not a valid URI.")])

    scheme = parts.scheme.lower()
    if scheme != "upi":
        return ParsedPayment(is_upi=False, scheme=scheme)

    # For upi://pay?..., urlsplit puts "pay" in netloc.
    action = (parts.netloc or parts.path.strip("/")).lower()
    result = ParsedPayment(is_upi=True, scheme=scheme, action=action)

    if action != "pay":
        result.issues.append(Issue("uri", "unsupported_action", f"Unsupported UPI action '{action or '(none)'}'. Only 'upi://pay' is supported."))

    try:
        params = parse_qs(parts.query, keep_blank_values=True, strict_parsing=False)
    except ValueError:
        params = {}
        result.issues.append(Issue("uri", "malformed_query", "The payment parameters could not be parsed."))

    lowered: dict[str, list[str]] = {}
    for key, values in params.items():
        lowered.setdefault(key.lower(), []).extend(values)

    for key, values in lowered.items():
        if len(values) > 1:
            result.duplicate_params.append(key)
        if key not in KNOWN_PARAMS:
            result.unknown_params.append(key)

    def first(key: str) -> str | None:
        vals = lowered.get(key)
        return vals[0] if vals else None

    result.payee_vpa = _clean(first("pa"), 256)
    result.payee_name = _clean(first("pn"), 100)
    result.amount = _clean(first("am"), 20)
    result.currency = _clean(first("cu"), 10)
    result.note = _clean(first("tn"), 200)
    result.merchant_code = _clean(first("mc"), 10)
    for key in ("tr", "mode", "purpose", "mam"):
        if (val := _clean(first(key), 80)) is not None:
            result.extra_params[key] = val

    # --- Field validation ---
    if not result.payee_vpa:
        result.issues.append(Issue("pa", "missing_payee", "The payee UPI ID (pa) is missing."))
    elif not VPA_RE.match(result.payee_vpa):
        result.issues.append(Issue("pa", "invalid_vpa", "The payee UPI ID is not in a valid name@provider format."))

    if not result.payee_name:
        result.notes.append("Payee name (pn) is not included in the QR.")

    if result.amount is not None:
        if not AMOUNT_RE.match(result.amount):
            result.issues.append(Issue("am", "invalid_amount", "The amount is not a valid number with up to 2 decimal places."))
        else:
            try:
                if Decimal(result.amount) <= 0:
                    result.issues.append(Issue("am", "non_positive_amount", "The amount is zero or negative."))
            except InvalidOperation:
                result.issues.append(Issue("am", "invalid_amount", "The amount could not be read as a number."))
    else:
        result.notes.append("No fixed amount is set; you will enter it in your UPI app.")

    if result.currency is not None:
        if not CURRENCY_RE.match(result.currency.upper()):
            result.issues.append(Issue("cu", "invalid_currency", "The currency code is malformed."))
        elif result.currency.upper() != "INR":
            result.issues.append(Issue("cu", "non_inr_currency", f"Currency is '{result.currency}', but UPI payments are in INR."))
    else:
        result.notes.append("Currency (cu) is not specified; UPI apps default to INR.")

    return result
