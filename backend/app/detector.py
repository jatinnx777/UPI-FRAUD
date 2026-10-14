"""Stage 4 - Explainable rule-based fraud detection.

Each rule inspects the parsed payment and may emit a Signal with a severity and
weight. The verdict is derived from the signals, so every result can be
explained by listing exactly which rules fired.

This is NOT a machine-learning model and has not been trained on any data.
"""

import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .upi_parser import ParsedPayment

SAFE, RISKY, LIKELY_FRAUD, UNABLE = "SAFE", "RISKY", "LIKELY_FRAUD", "UNABLE_TO_VERIFY"

RISKY_THRESHOLD = 25
FRAUD_THRESHOLD = 70

# Wording commonly used in payment-request scams. Matching one is a reason to
# double-check, not proof of fraud.
SCAM_PHRASES = [
    r"\breceive (money|payment|cash|prize|reward)\b",
    r"\b(prize|lottery|lucky draw|jackpot|winner)\b",
    r"\bkyc\b",
    r"\brefund\b",
    r"\bcash ?back\b",
    r"\b(processing|registration|release|verification) fee\b",
    r"\b(urgent|immediately|account (will be )?blocked)\b",
    r"\b(customer care|helpdesk|support desk)\b",
]

# Display names that claim to be an authority. Legitimate banks/government
# bodies rarely collect payment via a generic personal QR.
AUTHORITY_TERMS = [
    r"\b(rbi|reserve bank|npci|income tax|police|cyber cell|govt|government)\b",
    r"\b(sbi|hdfc|icici|axis|kotak|pnb) (bank )?(support|care|official|helpdesk)\b",
]

HIGH_AMOUNT = Decimal("100000")  # common per-transaction UPI limit


@dataclass
class Signal:
    id: str
    title: str
    detail: str
    severity: str  # info | low | medium | high | critical
    weight: int


def _load_demo_data() -> dict:
    path = Path(__file__).with_name("demo_data.json")
    return json.loads(path.read_text(encoding="utf-8"))


DEMO_DATA = _load_demo_data()
FLAGGED = {e["vpa"].lower(): e for e in DEMO_DATA["flagged_vpas"]}
TRUSTED = {e["vpa"].lower(): e for e in DEMO_DATA["trusted_payees"]}


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _matches_any(patterns: list[str], text: str) -> list[str]:
    hits = []
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            hits.append(m.group(0))
    return hits


def run_rules(p: ParsedPayment) -> list[Signal]:
    signals: list[Signal] = []
    vpa = (p.payee_vpa or "").lower()

    # --- Structural / validation issues from the parser ---
    for issue in p.issues:
        if issue.code == "invalid_vpa":
            signals.append(Signal("invalid_vpa", "Malformed payee UPI ID", issue.message, "high", 40))
        elif issue.code in ("invalid_amount", "non_positive_amount"):
            signals.append(Signal(issue.code, "Invalid amount", issue.message, "medium", 25))
        elif issue.code in ("non_inr_currency", "invalid_currency"):
            signals.append(Signal(issue.code, "Unexpected currency", issue.message, "medium", 25))
        elif issue.code in ("unsupported_action", "malformed_query"):
            signals.append(Signal(issue.code, "Unusual URI structure", issue.message, "medium", 25))

    if p.duplicate_params:
        signals.append(Signal(
            "duplicate_params", "Repeated payment fields",
            f"These fields appear more than once: {', '.join(sorted(p.duplicate_params))}. "
            "Different apps may read different values, which can hide the real recipient.",
            "high", 35,
        ))
    if p.unknown_params:
        signals.append(Signal(
            "unknown_params", "Non-standard fields present",
            f"Fields not defined by the UPI URI format: {', '.join(sorted(p.unknown_params))}.",
            "low", 10,
        ))

    # --- Synthetic demo indicator database ---
    if vpa in FLAGGED:
        signals.append(Signal(
            "demo_flagged_vpa", "Matches a demo fraud indicator",
            f"{FLAGGED[vpa]['reason']} (This is synthetic demo data, not real fraud intelligence.)",
            "critical", 80,
        ))

    # --- Claimed name vs. trusted reference (only when reference data exists) ---
    if vpa in TRUSTED and p.payee_name:
        ref = TRUSTED[vpa]["registered_name"]
        if _norm_name(ref) != _norm_name(p.payee_name):
            signals.append(Signal(
                "name_mismatch", "Payee name does not match reference",
                f"The QR shows the name \"{p.payee_name}\", but the demo reference record for this "
                f"UPI ID is \"{ref}\". Someone may be reusing a known ID under a different name.",
                "high", 35,
            ))

    # --- Content heuristics ---
    text = " ".join(filter(None, [p.payee_name, p.note]))
    if text:
        if hits := _matches_any(SCAM_PHRASES, text):
            signals.append(Signal(
                "scam_phrases", "Scam-associated wording",
                f"The name or note contains: {', '.join(repr(h) for h in hits)}. "
                "Remember: you never need to pay or scan a QR to RECEIVE money.",
                "medium", 20 + 5 * min(len(hits) - 1, 2),
            ))
        if hits := _matches_any(AUTHORITY_TERMS, text):
            signals.append(Signal(
                "authority_claim", "Claims to be an official authority",
                f"The payee presents itself as {', '.join(repr(h) for h in hits)}. Banks and government "
                "bodies do not ask for payments through personal QR codes.",
                "high", 35,
            ))

    if p.amount:
        try:
            amt = Decimal(p.amount)
            if amt > HIGH_AMOUNT:
                signals.append(Signal(
                    "high_amount", "Unusually large amount",
                    f"₹{amt:,.2f} exceeds the typical ₹1,00,000 per-transaction UPI limit.",
                    "medium", 20,
                ))
        except InvalidOperation:
            pass  # already reported by the parser

    # --- Neutral information (does not raise the risk score) ---
    for note in p.notes:
        signals.append(Signal("info", "Information", note, "info", 0))

    return signals


NEXT_STEPS = {
    SAFE: [
        "Confirm the payee name shown in your UPI app matches who you intend to pay.",
        "Check the amount before entering your UPI PIN.",
        "Only enter your PIN when YOU are sending money - never to receive it.",
    ],
    RISKY: [
        "Do not pay yet. Verify the recipient through a contact you already trust (not one given in this QR or message).",
        "Compare the name your UPI app shows against the expected recipient.",
        "If anyone is pressuring you to pay quickly, stop and verify independently.",
    ],
    LIKELY_FRAUD: [
        "Do not make this payment.",
        "Do not share your UPI PIN, OTP or card details with anyone.",
        "Report suspected fraud at the National Cyber Crime portal (cybercrime.gov.in) or helpline 1930, and inform your bank.",
    ],
    UNABLE: [
        "Do not rely on this QR. Ask the recipient for a fresh, clear UPI QR or their UPI ID.",
        "If the QR opens a website instead of a UPI app, do not enter any banking details there.",
    ],
}

EXPLANATIONS = {
    SAFE: "None of the available checks found a significant warning sign. This does not prove the recipient is legitimate.",
    RISKY: "One or more warning signs were found. The payment may still be genuine, but it needs independent verification first.",
    LIKELY_FRAUD: "Strong warning signs were found, including evidence from the configured indicator checks. This request is likely fraudulent.",
    UNABLE: "There was not enough valid UPI payment information to assess this QR.",
}


def assess(p: ParsedPayment) -> dict:
    # Without a UPI payment URI or payee, we cannot assess risk - never call it safe.
    if not p.is_upi or not p.payee_vpa:
        reason = (
            "This QR does not contain a UPI payment request."
            if not p.is_upi else "The QR is a UPI URI but has no payee UPI ID (pa)."
        )
        sig = Signal("not_verifiable", "Cannot verify", reason, "info", 0)
        if not p.is_upi and p.scheme in ("http", "https"):
            sig = Signal("web_link", "QR contains a web link",
                         "This QR opens a website rather than a UPI payment. The link was not opened.", "medium", 0)
        return _result(UNABLE, 0, [sig])

    signals = run_rules(p)
    score = min(100, sum(s.weight for s in signals))
    has_critical = any(s.severity == "critical" for s in signals)

    if has_critical or score >= FRAUD_THRESHOLD:
        verdict = LIKELY_FRAUD
    elif score >= RISKY_THRESHOLD:
        verdict = RISKY
    else:
        verdict = SAFE
    return _result(verdict, score, signals)


def _result(verdict: str, score: int, signals: list[Signal]) -> dict:
    return {
        "verdict": verdict,
        "risk_score": score,
        "signals": [asdict(s) for s in signals],
        "explanation": EXPLANATIONS[verdict],
        "next_steps": NEXT_STEPS[verdict],
    }
