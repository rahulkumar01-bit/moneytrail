"""
app.py
------
A thin Flask API around the existing core/ pipeline (extract, html_gen,
pdf_gen). One real endpoint:

    POST /process
        multipart/form-data body with a field named "file" containing
        the .xlsx workbook.

        Response (200):
        {
          "status": "ok",
          "html_filename": "...", "html_base64": "...",
          "pdf_filename": "...",  "pdf_base64": "..."
        }

        Response (400) on a bad/unrecognized workbook:
        {"status": "error", "message": "..."}

Also:
    GET /health   -- liveness check (handy for confirming the free
                      instance has woken up after sleeping)

This is deliberately stateless and does no email of its own -- the
Google Apps Script agent (see automation/MoneytrailAgent.gs) is
responsible for watching Gmail and sending replies. This service's only
job is: take an xlsx, hand back the two generated files.
"""

import base64
import os
import tempfile
import traceback
from pathlib import Path

from flask import Flask, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.extract import extract_data, ExtractionError
from core.html_gen import generate_html
from core.pdf_gen import generate_pdf

app = Flask(__name__)

MAX_UPLOAD_MB = 15
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/process")
def process():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file field named 'file' in the request."}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"status": "error", "message": "Empty filename."}), 400
    if not upload.filename.lower().endswith(".xlsx"):
        return jsonify({"status": "error", "message": "File must be a .xlsx workbook."}), 400

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_path = tmp_path / upload.filename
        upload.save(src_path)

        try:
            data = extract_data(src_path)
        except ExtractionError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        except Exception:
            return jsonify({
                "status": "error",
                "message": "Unexpected error reading the workbook.",
                "detail": traceback.format_exc(),
            }), 500

        base_name = Path(upload.filename).stem
        html_path = tmp_path / f"{base_name}_money_trail.html"
        pdf_path = tmp_path / f"{base_name}_money_trail.pdf"

        try:
            generate_html(data, html_path)
            generate_pdf(data, pdf_path)
        except Exception:
            return jsonify({
                "status": "error",
                "message": "Unexpected error generating the outputs.",
                "detail": traceback.format_exc(),
            }), 500

        html_b64 = base64.b64encode(html_path.read_bytes()).decode("ascii")
        pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode("ascii")

    return jsonify({
        "status": "ok",
        "html_filename": html_path.name,
        "html_base64": html_b64,
        "pdf_filename": pdf_path.name,
        "pdf_base64": pdf_b64,
    })


if __name__ == "__main__":
    # Local testing only. In production, Render runs this via gunicorn
    # (see Procfile).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
