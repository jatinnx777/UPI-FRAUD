"""End-to-end tests: real image -> decode -> parse -> detect -> verdict."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.upi_parser import parse_upi_uri
from app.detector import assess

SAMPLES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"
client = TestClient(app)


def upload(name: str):
    data = (SAMPLES / name).read_bytes()
    return client.post("/api/verify/qr", files={"file": (name, data, "image/png")})


@pytest.mark.parametrize("name,verdict", [
    ("1_safe_demo.png", "SAFE"),
    ("2_risky_demo.png", "RISKY"),
    ("3_fraud_demo.png", "LIKELY_FRAUD"),
    ("4_unsupported_demo.png", "UNABLE_TO_VERIFY"),
    ("5_unreadable_demo.png", "UNABLE_TO_VERIFY"),
])
def test_sample_verdicts(name, verdict):
    r = upload(name)
    assert r.status_code == 200
    assert r.json()["verdict"] == verdict
    assert "not a guarantee" in r.json()["disclaimer"]


def test_safe_sample_fields():
    body = upload("1_safe_demo.png").json()
    assert body["payment"]["payee_vpa"] == "freshmart.demo@demobank"
    assert body["payment"]["payee_name"] == "FreshMart Demo Store"
    assert body["payment"]["amount"] == "250.00"
    assert body["payment"]["currency"] == "INR"


def test_rejects_non_image():
    r = client.post("/api/verify/qr", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unsupported_type"


def test_rejects_fake_png_extension():
    r = client.post("/api/verify/qr", files={"file": ("x.png", b"not really a png", "image/png")})
    assert r.status_code == 400


def test_minimal_unknown_payee_is_not_fraud():
    # An unfamiliar but well-formed UPI ID with no name/amount must not be flagged.
    result = assess(parse_upi_uri("upi://pay?pa=someone123@unknownpsp"))
    assert result["verdict"] == "SAFE"


def test_malformed_vpa_is_risky():
    result = assess(parse_upi_uri("upi://pay?pa=not-a-vpa&pn=Shop&cu=INR"))
    assert result["verdict"] == "RISKY"


def test_duplicate_payee_and_bad_currency():
    result = assess(parse_upi_uri("upi://pay?pa=a.b@okbank&pa=x.y@okbank&cu=USD&am=10"))
    ids = {s["id"] for s in result["signals"]}
    assert {"duplicate_params", "non_inr_currency"} <= ids
    assert result["verdict"] in ("RISKY", "LIKELY_FRAUD")


def test_missing_payee_unable():
    assert assess(parse_upi_uri("upi://pay?pn=Shop&am=10"))["verdict"] == "UNABLE_TO_VERIFY"
