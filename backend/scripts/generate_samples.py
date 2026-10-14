"""Generate the synthetic demo QR images used by the frontend and tests.

All UPI IDs use the fictional '@demobank' handle and are NOT real accounts.

Usage (from the backend folder):  python scripts/generate_samples.py
"""

from pathlib import Path

import cv2
import numpy as np
import qrcode

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"

SAMPLES = {
    "1_safe_demo.png":
        "upi://pay?pa=freshmart.demo@demobank&pn=FreshMart%20Demo%20Store&am=250.00&cu=INR&tn=Groceries",
    "2_risky_demo.png":
        "upi://pay?pa=freshmart.demo@demobank&pn=FreshMart%20Refund%20Desk&am=4999.00&cu=INR&tn=Refund%20for%20cancelled%20order",
    "3_fraud_demo.png":
        "upi://pay?pa=prize.claim.demo@demobank&pn=Lucky%20Draw%20Rewards&am=9999.00&cu=INR&tn=Pay%20fee%20to%20receive%20prize%20money",
    "4_unsupported_demo.png":
        "https://example.com/claim-your-reward",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in SAMPLES.items():
        qrcode.make(payload, box_size=8, border=4).save(OUT / name)
        print("wrote", name)

    # An image with no QR code at all, to demonstrate the 'unreadable' path.
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    noise = cv2.GaussianBlur(noise, (9, 9), 0)
    cv2.putText(noise, "NO QR", (70, 165), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3)
    cv2.imwrite(str(OUT / "5_unreadable_demo.png"), noise)
    print("wrote 5_unreadable_demo.png")


if __name__ == "__main__":
    main()
