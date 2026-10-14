"""FastAPI entry point: Upload QR -> Decode -> Parse -> Detect -> Verdict."""

import logging

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .decoder import MAX_FILE_BYTES, DecodeError, decode_qr
from .detector import UNABLE, assess
from .upi_parser import parse_upi_uri

# Log only event types, never payment payloads or UPI IDs.
logger = logging.getLogger("upi_verify")
logging.basicConfig(level=logging.INFO)

DISCLAIMER = (
    "This result is a risk assessment based on available information, not a guarantee that the "
    "payment is legitimate. Verify the recipient and amount in your official UPI app before "
    "authorizing payment."
)

app = FastAPI(title="UPI QR Fraud Verification API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _unable(code: str, message: str, status: int = 200, payload: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "status": "error",
        "error": {"code": code, "message": message},
        "verdict": UNABLE,
        "risk_score": None,
        "decoded_payload": payload,
        "payment": None,
        "signals": [],
        "explanation": message,
        "next_steps": [
            "Upload a clear PNG or JPG image of the full QR code.",
            "If the problem persists, ask the recipient for their UPI ID and verify it in your UPI app.",
        ],
        "disclaimer": DISCLAIMER,
    })


@app.post("/api/verify/qr")
async def verify_qr(file: UploadFile = File(...)):
    # Read at most limit+1 bytes so oversized uploads are rejected without loading them fully.
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        decoded = decode_qr(data, file.content_type)
    except DecodeError as e:
        logger.info("decode failed: %s", e.code)
        status = 400 if e.code in ("empty_file", "file_too_large", "unsupported_type") else 200
        return _unable(e.code, e.message, status)
    except Exception:
        logger.exception("unexpected decoder failure")
        return _unable("internal_error", "Something went wrong while reading the image.", 500)

    parsed = parse_upi_uri(decoded.payload)
    result = assess(parsed)
    logger.info("verified qr: verdict=%s", result["verdict"])

    return {
        "status": "ok",
        "decoded_payload": decoded.payload[:1000],
        "payload_type": "upi_payment" if parsed.is_upi else (parsed.scheme or "text"),
        "payment": parsed.to_dict() if parsed.is_upi else None,
        "validation_issues": [vars(i) for i in parsed.issues],
        **result,
        "disclaimer": DISCLAIMER,
    }
