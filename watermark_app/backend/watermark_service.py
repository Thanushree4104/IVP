"""
watermark_service.py
====================
Service layer that wraps watermark_core.py.
Called by app.py routes. Handles embed and verify operations.
"""

import numpy as np
import cv2
import os
import io
import base64
from PIL import Image

from watermark_core import (
    text_to_payload,
    logo_to_payload,
    payload_to_logo,
    DCTWatermark,
    DWTWatermark,
    HybridWatermark,
    compute_metrics,
    LOGO_SIZE,
)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _file_to_np(file_storage, size=256):
    """Convert a Flask FileStorage (image) to an RGB float64 numpy array."""
    img_bytes = file_storage.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image. Please upload a valid PNG/JPG.")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    # img = cv2.resize(img, (size, size))
    return img.astype(np.float64)


def _np_to_b64(img_np):
    """Convert a float64 RGB numpy array to a base64-encoded PNG string."""
    arr = np.clip(img_np, 0, 255).astype(np.uint8)
    pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _np_to_bytes(img_np):
    """Convert a float64 RGB numpy array to raw PNG bytes for download."""
    arr = np.clip(img_np, 0, 255).astype(np.uint8)
    pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _logo_file_to_np(file_storage):
    """Read an uploaded logo FileStorage into a grayscale numpy array."""
    img_bytes = file_storage.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Could not decode logo image.")
    img = cv2.resize(img, (LOGO_SIZE, LOGO_SIZE))
    return img


def _get_embedder(method):
    method = method.upper()
    if method == "DCT":
        return DCTWatermark(alpha=25)
    elif method == "DWT":
        return DWTWatermark(alpha=20, band="LH")
    elif method == "HYBRID":
        return HybridWatermark(alpha=18)
    else:
        raise ValueError(f"Unknown method: {method}. Choose DCT, DWT, or HYBRID.")


# ─────────────────────────────────────────────
#  EMBED
# ─────────────────────────────────────────────

def embed_text_watermark(image_file, password, watermark_text, method):
    """
    Embed a text watermark into an image.
    Returns dict with base64 image, metrics, and download bytes.
    """
    original = _file_to_np(image_file)
    wm_bits = text_to_payload(watermark_text, password)

    embedder = _get_embedder(method)
    watermarked = embedder.embed(original, wm_bits)

    metrics = compute_metrics(original, watermarked)
    verify_result = embedder.verify(watermarked, wm_bits)

    return {
        "watermarked_b64": _np_to_b64(watermarked),
        "watermarked_bytes": _np_to_bytes(watermarked),
        "metrics": metrics,
        "ncc": verify_result["ncc"],
        "detected": verify_result["detected"],
        "method": method.upper(),
    }


def embed_logo_watermark(image_file, password, logo_file, method):
    """
    Embed a logo watermark into an image.
    Returns dict with base64 image, metrics, and download bytes.
    """
    original = _file_to_np(image_file)

    # Build payload from the uploaded logo
    logo_np = _logo_file_to_np(logo_file)
    logo_bin = (logo_np > 128).astype(np.uint8)

    # Use the core logo_to_payload but inject our logo bytes
    from watermark_core import aes_encrypt, rs_encode
    raw_bytes = np.packbits(logo_bin.flatten()).tobytes()
    encrypted = aes_encrypt(raw_bytes, password, label="logo_wm")
    protected = rs_encode(encrypted)
    logo_bits = np.unpackbits(np.frombuffer(protected, dtype=np.uint8)).astype(np.float64)

    embedder = _get_embedder(method)
    watermarked = embedder.embed(original, logo_bits)

    metrics = compute_metrics(original, watermarked)
    verify_result = embedder.verify(watermarked, logo_bits)

    return {
        "watermarked_b64": _np_to_b64(watermarked),
        "watermarked_bytes": _np_to_bytes(watermarked),
        "metrics": metrics,
        "ncc": verify_result["ncc"],
        "detected": verify_result["detected"],
        "method": method.upper(),
    }


# ─────────────────────────────────────────────
#  VERIFY
# ─────────────────────────────────────────────

def verify_text_watermark(watermarked_file, password, watermark_text, method):
    """
    Verify whether a text watermark is present in the image.
    """
    watermarked = _file_to_np(watermarked_file)
    wm_bits = text_to_payload(watermark_text, password)

    embedder = _get_embedder(method)
    result = embedder.verify(watermarked, wm_bits)

    return {
        "ncc": result["ncc"],
        "detected": result["detected"],
        "method": method.upper(),
        "threshold": 0.05,
    }


def verify_logo_watermark(watermarked_file, password, logo_file, method):
    """
    Verify whether a logo watermark is present in the image.
    Also reconstructs the extracted logo for visual comparison.
    """
    watermarked = _file_to_np(watermarked_file)

    logo_np = _logo_file_to_np(logo_file)
    logo_bin = (logo_np > 128).astype(np.uint8)

    from watermark_core import aes_encrypt, rs_encode
    raw_bytes = np.packbits(logo_bin.flatten()).tobytes()
    encrypted = aes_encrypt(raw_bytes, password, label="logo_wm")
    protected = rs_encode(encrypted)
    logo_bits = np.unpackbits(np.frombuffer(protected, dtype=np.uint8)).astype(np.float64)

    embedder = _get_embedder(method)
    result = embedder.verify(watermarked, logo_bits)

    # Try to reconstruct extracted logo for display
    try:
        extracted_logo = _reconstruct_logo(watermarked, embedder, logo_bits, password)
        logo_b64 = _np_to_b64(
            np.stack([extracted_logo * 255] * 3, axis=-1).astype(np.float64)
        )
    except Exception:
        logo_b64 = None

    return {
        "ncc": result["ncc"],
        "detected": result["detected"],
        "method": method.upper(),
        "threshold": 0.05,
        "extracted_logo_b64": logo_b64,
    }


def _reconstruct_logo(watermarked, embedder, logo_bits, password):
    """Pull raw bit values from the frequency band and reconstruct logo."""
    if isinstance(embedder, HybridWatermark):
        luma = embedder._luma(watermarked)
        _, LH, _, _ = embedder._dwt._fwd(luma)
        ext = embedder._extract_from_band(LH)
    elif isinstance(embedder, DCTWatermark):
        from scipy.fft import dctn
        from watermark_core import MID_MASK
        luma = embedder._luma(watermarked)
        H, W = luma.shape
        bs = embedder.block_size
        ext_list = []
        for by in range(H // bs):
            for bx in range(W // bs):
                r0, c0 = by * bs, bx * bs
                coeffs = dctn(luma[r0:r0+bs, c0:c0+bs], norm='ortho')
                for (u, v) in MID_MASK:
                    ext_list.append(coeffs[u, v])
        ext = np.array(ext_list)
    elif isinstance(embedder, DWTWatermark):
        luma = watermarked[:, :, 0].astype(np.float64)
        _, LH, _, _ = embedder._fwd(luma)
        ext = LH.flatten()
    else:
        return np.zeros((LOGO_SIZE, LOGO_SIZE), dtype=np.uint8)

    bits = (ext[:len(logo_bits)] > 0).astype(np.float64)
    return payload_to_logo(bits, password)
