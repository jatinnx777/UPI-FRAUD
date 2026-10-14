# QR Shield: AI-Powered UPI Payment Fraud Detection & Verification (Prototype)

QR Shield checks a UPI QR code **before** you pay. It does not make payments.

```
Upload QR → Decode → Parse & Validate → Detect Suspicious Signals → Explain Verdict → Recommend Next Action
```

> **What this prototype is not:** It is not a payment gateway. It never starts a payment, never asks for a UPI PIN and never opens links found in a QR. Fraud detection is **rule-based**. No ML model has been trained yet. Every "known fraud" or "trusted merchant" record is **synthetic demo data** (see `backend/app/demo_data.json`).

## Folder structure

```
UPI FRAUD/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app and POST /api/verify/qr endpoint
│   │   ├── decoder.py       # Stage 2: file validation + OpenCV QR decoding
│   │   ├── upi_parser.py    # Stage 3: upi://pay URI parsing and field validation
│   │   ├── detector.py      # Stage 4: explainable rule engine, verdict, next steps
│   │   └── demo_data.json   # SYNTHETIC flagged IDs and trusted-payee reference
│   ├── scripts/generate_samples.py   # builds the demo QR images
│   ├── tests/test_pipeline.py        # end-to-end tests on real images
│   └── requirements.txt
└── frontend/                # React (Vite) single-page app
    ├── public/samples/      # generated demo QR images
    └── src/ (App.jsx, api.js, styles.css, main.jsx)
```

## Setup and run

You need Python 3.10 or newer and Node.js 18 or newer.

**1. Backend** (terminal 1)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python scripts/generate_samples.py   # optional: the sample images are already included
uvicorn app.main:app --reload --port 8000
```
API docs are at http://127.0.0.1:8000/docs.

**2. Frontend** (terminal 2)
```bash
cd frontend
npm install
npm run dev
```
Then open **http://localhost:5173**. The dev server forwards `/api` requests to the backend on port 8000.

**3. Tests**
```bash
cd backend
python -m pytest -q
```

## Deploying to Vercel

The repo deploys as a single Vercel project:
- The React app is built from `frontend/` and served as static files.
- The FastAPI backend runs as a Python serverless function at `api/index.py`, which imports `backend/app`.
- `vercel.json` sends every `/api/*` request to that function, so the frontend calls the API on the same domain and needs no CORS setup.

Deployment files: `vercel.json`, `.vercelignore`, `api/index.py` and the root `requirements.txt` (runtime dependencies only).

**Option A: from GitHub (recommended)**
1. Push this folder to a GitHub repository.
2. On vercel.com, choose **Add New → Project** and import the repository.
3. Keep **Root Directory** as the repository root and leave the framework preset as **Other**. The build settings are taken from `vercel.json`.
4. Click **Deploy**. Every later push redeploys automatically.

**Option B: from the command line**
```bash
npm i -g vercel
vercel login
vercel          # creates a preview deployment
vercel --prod   # deploys to production
```

**Limits to know**
- Vercel rejects request bodies over 4.5 MB, so uploads are capped at 4 MB.
- The first request after the function has been idle can take a few seconds while OpenCV loads (a cold start).

## Demo cases

On the page, click any button under **"Try a synthetic demo QR"**, then click **Decode & Check Risk**. Each sample is a real PNG that goes through the full decoding pipeline.

| Sample | QR content (summary) | Verdict | Why |
|---|---|---|---|
| Clean merchant QR | `freshmart.demo@demobank`, name matches the reference, ₹250 | **Safe** (0) | No warning indicators |
| Name mismatch + refund | Same UPI ID, but named "FreshMart Refund Desk", note "Refund…" | **Risky** (55) | Name does not match the reference record; the note uses scam wording |
| Demo flagged "prize" account | `prize.claim.demo@demobank`, "receive prize money" | **Likely Fraud** | Matches a synthetic fraud indicator; uses scam wording |
| QR with a web link | `https://example.com/...` | **Unable to Verify** | Not a UPI payment. The link is shown but never opened |
| Image with no QR | Noise image | **Unable to Verify** | No QR detected |

You can also upload your own PNG or JPG screenshots of UPI QR codes.

## API

`POST /api/verify/qr` accepts a multipart field named `file` (a PNG or JPEG of at most 4 MB). It returns:

```json
{
  "status": "ok",
  "verdict": "RISKY",              // SAFE | RISKY | LIKELY_FRAUD | UNABLE_TO_VERIFY
  "risk_score": 55,
  "payment": { "payee_vpa": "...", "payee_name": "...", "amount": "4999.00", "currency": "INR", "note": "..." },
  "signals": [ { "id": "name_mismatch", "title": "...", "detail": "...", "severity": "high", "weight": 35 } ],
  "explanation": "...",
  "next_steps": ["..."],
  "decoded_payload": "upi://pay?...",
  "disclaimer": "..."
}
```

The API rejects an invalid file type, a file over the size limit or an empty file with HTTP 400. If the QR cannot be read, it returns HTTP 200 with `"verdict": "UNABLE_TO_VERIFY"` and an `error` object.

## How the verdict is decided

The verdict comes from a fixed set of rules in `detector.py`. Each rule that fires adds a signal with a severity and a weight:

| Rule | Severity / weight |
|---|---|
| UPI ID matches the synthetic flagged list | critical / 80 |
| Payee UPI ID has an invalid format | high / 40 |
| Same field appears more than once (e.g. two `pa` values) | high / 35 |
| Name in the QR differs from the trusted reference for that UPI ID | high / 35 |
| Name claims to be an authority (bank support, RBI, police…) | high / 35 |
| Currency is not INR, or the amount is invalid or not positive | medium / 25 |
| Scam wording ("receive money", prize, KYC, refund, fee…) | medium / 20–30 |
| Amount above ₹1,00,000 | medium / 20 |
| Non-standard URI fields | low / 10 |
| Missing optional fields (name, amount, currency) | info / 0 |

These weights are added up into a risk score:

- Any **critical** signal, or a score of 70 or more, gives **Likely Fraud**.
- A score from 25 to 69 gives **Risky**.
- A score below 25 gives **Safe**.
- No UPI payload, or no payee ID, gives **Unable to Verify**. This case is never reported as Safe.

Some things deliberately do **not** raise the risk score:
- A UPI ID or payment app handle the system does not recognise.
- Missing optional fields.

## Privacy and safety notes

- The server logs only event types and verdicts. It never logs UPI IDs, names or payloads.
- Uploaded images are processed in memory and never stored.
- The upload is checked by its file signature (magic bytes), not just its extension.
- Decoded text is shown only as plain text. Links are never opened or fetched.

## Future work

- Verify a UPI ID or payment link directly. Add new endpoints next to `/api/verify/qr`, reuse `upi_parser` and `detector`, and add a function in `frontend/src/api.js`.
- Replace `demo_data.json` with a real database (for example Supabase or PostgreSQL) holding verified sources.
- Add an ML risk model, once a real labelled dataset is available.
