"""
app.py
======
Flask backend for the Digital Image Watermarking Dashboard.
Serves HTML templates and exposes REST API endpoints.

Run:
    pip install flask flask-cors pillow opencv-python-headless scipy
                scikit-image cryptography numpy
    python app.py
"""

import os
import io
from flask import (
    Flask, request, jsonify, send_file,
    render_template, send_from_directory
)
from flask_cors import CORS

from watermark_service import (
    embed_text_watermark,
    embed_logo_watermark,
    verify_text_watermark,
    verify_logo_watermark,
)

# ─────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)
CORS(app)

# In-memory store for last watermarked image (for download)
_download_store: dict = {}


# ─────────────────────────────────────────────
#  PAGE ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/embed")
def embed_page():
    return render_template("embed.html")


@app.route("/verify")
def verify_page():
    return render_template("verify.html")


# ─────────────────────────────────────────────
#  API — EMBED
# ─────────────────────────────────────────────

@app.route("/api/embed", methods=["POST"])
def api_embed():
    """
    POST /api/embed
    Form fields:
      - image        : image file
      - password     : AES password
      - wm_type      : "text" | "logo"
      - watermark_text : (if wm_type == text)
      - logo         : (if wm_type == logo) logo image file
      - method       : "DCT" | "DWT" | "HYBRID"
    """
    try:
        image = request.files.get("image")
        if image is None:
            return jsonify({"error": "No image uploaded."}), 400

        password = request.form.get("password", "").strip()
        if not password:
            return jsonify({"error": "Password is required."}), 400

        wm_type = request.form.get("wm_type", "text").lower()
        method = request.form.get("method", "HYBRID").upper()

        if wm_type == "text":
            wm_text = request.form.get("watermark_text", "").strip()
            if not wm_text:
                return jsonify({"error": "Watermark text is required."}), 400
            result = embed_text_watermark(image, password, wm_text, method)

        elif wm_type == "logo":
            logo = request.files.get("logo")
            if logo is None:
                return jsonify({"error": "Logo image is required for logo watermarking."}), 400
            result = embed_logo_watermark(image, password, logo, method)

        else:
            return jsonify({"error": f"Unknown wm_type: {wm_type}"}), 400

        # Stash bytes for download endpoint
        _download_store["last"] = result["watermarked_bytes"]

        return jsonify({
            "success": True,
            "watermarked_b64": result["watermarked_b64"],
            "metrics": result["metrics"],
            "ncc": result["ncc"],
            "detected": result["detected"],
            "method": result["method"],
        })

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        app.logger.exception("Embed error")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ─────────────────────────────────────────────
#  API — DOWNLOAD
# ─────────────────────────────────────────────

@app.route("/api/download", methods=["GET"])
def api_download():
    """GET /api/download — Download the last watermarked image."""
    data = _download_store.get("last")
    if data is None:
        return jsonify({"error": "No watermarked image available. Run embed first."}), 404
    return send_file(
        io.BytesIO(data),
        mimetype="image/png",
        as_attachment=True,
        download_name="watermarked_image.png",
    )


# ─────────────────────────────────────────────
#  API — VERIFY
# ─────────────────────────────────────────────

@app.route("/api/verify", methods=["POST"])
def api_verify():
    """
    POST /api/verify
    Form fields:
      - image        : watermarked image file
      - password     : AES password
      - wm_type      : "text" | "logo"
      - watermark_text : (if wm_type == text)
      - logo         : (if wm_type == logo)
      - method       : "DCT" | "DWT" | "HYBRID"
    """
    try:
        image = request.files.get("image")
        if image is None:
            return jsonify({"error": "No image uploaded."}), 400

        password = request.form.get("password", "").strip()
        if not password:
            return jsonify({"error": "Password is required."}), 400

        wm_type = request.form.get("wm_type", "text").lower()
        method = request.form.get("method", "HYBRID").upper()

        if wm_type == "text":
            wm_text = request.form.get("watermark_text", "").strip()
            if not wm_text:
                return jsonify({"error": "Watermark text is required."}), 400
            result = verify_text_watermark(image, password, wm_text, method)

        elif wm_type == "logo":
            logo = request.files.get("logo")
            if logo is None:
                return jsonify({"error": "Logo image is required."}), 400
            result = verify_logo_watermark(image, password, logo, method)

        else:
            return jsonify({"error": f"Unknown wm_type: {wm_type}"}), 400

        return jsonify({
            "success": True,
            "ncc": result["ncc"],
            "detected": result["detected"],
            "method": result["method"],
            "threshold": result["threshold"],
            "extracted_logo_b64": result.get("extracted_logo_b64"),
        })

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        app.logger.exception("Verify error")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  WatermarkShield — Digital Watermarking Dashboard")
    print("  Running at: http://127.0.0.1:5000")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000)
