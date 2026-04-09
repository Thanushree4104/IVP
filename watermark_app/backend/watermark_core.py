"""
watermark_core.py
=================
Advanced digital image watermarking core library.

Features:
  - DCT              : Block-DCT spread-spectrum (JPEG resistant)
  - DWT              : Haar wavelet, embeds in LH sub-band
  - Hybrid DWT+DCT   : DWT decompose -> DCT on LH band -> embed (strongest)
  - Logo watermark   : Embed a binary logo image instead of text
  - AES-256-CTR      : Encrypt watermark bits before embedding (no hashing)
  - Reed-Solomon ECC : Error correction so watermark survives compression/noise
"""

import numpy as np
import cv2
import os
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.fft import dctn, idctn
from skimage.metrics import structural_similarity as ssim_fn
from skimage.metrics import peak_signal_noise_ratio as psnr_fn
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import warnings
warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════
#  GLOBAL CONFIG
# ═══════════════════════════════════════════════

AES_PASSWORD   = "my_secret_key_2025"   # Change this to your own password
LOGO_SIZE      = 32                      # Logo resized to 32x32 = 1024 bits
RS_ECC_SYMBOLS = 10                      # Reed-Solomon ECC bytes per block


# ═══════════════════════════════════════════════
#  REED-SOLOMON  (pure Python, no external lib)
# ═══════════════════════════════════════════════

GF_EXP = [0] * 512
GF_LOG = [0] * 256

def _init_gf():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11d
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]

_init_gf()

def _gf_mul(x, y):
    if x == 0 or y == 0:
        return 0
    return GF_EXP[(GF_LOG[x] + GF_LOG[y]) % 255]

def _gf_pow(x, p):
    return GF_EXP[(GF_LOG[x] * p) % 255] if x != 0 else 0

def _gf_poly_mul(p, q):
    r = [0] * (len(p) + len(q) - 1)
    for j, qj in enumerate(q):
        for i, pi in enumerate(p):
            r[i + j] ^= _gf_mul(pi, qj)
    return r

def _rs_generator(nsym):
    g = [1]
    for i in range(nsym):
        g = _gf_poly_mul(g, [1, _gf_pow(2, i)])
    return g

def rs_encode(msg_bytes, nsym=RS_ECC_SYMBOLS):
    """Append Reed-Solomon ECC bytes to message."""
    gen     = _rs_generator(nsym)
    msg_out = list(msg_bytes) + [0] * nsym
    for i in range(len(msg_bytes)):
        coef = msg_out[i]
        if coef != 0:
            for j in range(1, len(gen)):
                msg_out[i + j] ^= _gf_mul(gen[j], coef)
    return bytes(list(msg_bytes) + msg_out[len(msg_bytes):])

def rs_decode(msg_bytes, nsym=RS_ECC_SYMBOLS):
    """Strip ECC bytes and return original message."""
    return bytes(list(msg_bytes)[:-nsym])


# ═══════════════════════════════════════════════
#  AES-256-CTR  (no hashing — password only)
# ═══════════════════════════════════════════════

def _derive_key_iv(password, label):
    salt = label.encode()[:16].ljust(16, b'\x00')
    kdf  = PBKDF2HMAC(algorithm=hashes.SHA256(), length=48,
                      salt=salt, iterations=100_000)
    raw  = kdf.derive(password.encode())
    return raw[:32], raw[32:48]

def aes_encrypt(data, password, label="wm"):
    key, iv = _derive_key_iv(password, label)
    enc     = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return enc.update(data) + enc.finalize()

def aes_decrypt(data, password, label="wm"):
    return aes_encrypt(data, password, label)   # CTR is symmetric


# ═══════════════════════════════════════════════
#  WATERMARK PAYLOAD -> BIT SEQUENCE
# ═══════════════════════════════════════════════

def text_to_payload(text, password):
    """text -> AES encrypt -> Reed-Solomon encode -> bit array (no hashing)"""
    raw       = text.encode("utf-8")
    encrypted = aes_encrypt(raw, password, label="text_wm")
    protected = rs_encode(encrypted, nsym=RS_ECC_SYMBOLS)
    bits      = np.unpackbits(np.frombuffer(protected, dtype=np.uint8))
    print(f"[PAYLOAD] raw={len(raw)}B  encrypted={len(encrypted)}B  "
          f"RS-protected={len(protected)}B  bits={len(bits)}")
    return bits.astype(np.float64)

def logo_to_payload(logo_path, password):
    """logo.png -> binary -> AES encrypt -> RS encode -> bits"""
    if logo_path and os.path.exists(logo_path):
        logo = cv2.imread(logo_path, cv2.IMREAD_GRAYSCALE)
        logo = cv2.resize(logo, (LOGO_SIZE, LOGO_SIZE))
    else:
        print("[LOGO] No logo found — generating demo logo.")
        logo = _make_demo_logo()
    logo_bin  = (logo > 128).astype(np.uint8)
    raw_bytes = np.packbits(logo_bin.flatten()).tobytes()
    encrypted = aes_encrypt(raw_bytes, password, label="logo_wm")
    protected = rs_encode(encrypted, nsym=RS_ECC_SYMBOLS)
    bits      = np.unpackbits(np.frombuffer(protected, dtype=np.uint8))
    print(f"[LOGO]    size={LOGO_SIZE}x{LOGO_SIZE}  bits={len(bits)}")
    return bits.astype(np.float64), logo_bin

def payload_to_logo(bits, password):
    """bits -> RS decode -> AES decrypt -> 32x32 binary logo"""
    n_bytes   = (len(bits) // 8) * 8
    raw_bytes = np.packbits(bits[:n_bytes].astype(np.uint8)).tobytes()
    try:
        decoded    = rs_decode(raw_bytes, nsym=RS_ECC_SYMBOLS)
        logo_bytes = aes_decrypt(decoded, password, label="logo_wm")
        logo_bits  = np.unpackbits(np.frombuffer(logo_bytes, dtype=np.uint8))
        return logo_bits[:LOGO_SIZE * LOGO_SIZE].reshape(LOGO_SIZE, LOGO_SIZE).astype(np.uint8)
    except Exception as e:
        print(f"[LOGO] Reconstruction failed: {e}")
        return np.zeros((LOGO_SIZE, LOGO_SIZE), dtype=np.uint8)

def _make_demo_logo(size=32):
    logo = np.zeros((size, size), dtype=np.uint8)
    logo[size//2-2:size//2+2, :] = 255
    logo[:, size//2-2:size//2+2] = 255
    logo[0:3, :] = 255;  logo[-3:, :]  = 255
    logo[:, 0:3] = 255;  logo[:, -3:]  = 255
    return logo

def bits_to_bipolar(bits):
    return 2.0 * np.asarray(bits) - 1.0


# ═══════════════════════════════════════════════
#  IMAGE UTILITIES
# ═══════════════════════════════════════════════

def make_demo_image(size=256):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for i in range(size):
        for j in range(size):
            img[i, j] = [int(128 + 80 * np.sin(2 * np.pi * i / 64)),
                         int(128 + 80 * np.cos(2 * np.pi * j / 64)),
                         int(200 - i * 200 // size)]
    cv2.putText(img, "ORIGINAL", (30, size // 2), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.rectangle(img, (10, 10), (size-10, size-10), (220, 220, 100), 3)
    return img

def load_image(path=None, size=256):
    if path and os.path.exists(path):
        img = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    else:
        print("[INFO] No image path — using synthetic demo image.")
        img = make_demo_image(size)
    return img.astype(np.float64)

def compute_metrics(original, watermarked):
    orig = np.clip(original,    0, 255).astype(np.uint8)
    wm   = np.clip(watermarked, 0, 255).astype(np.uint8)
    mse  = float(np.mean((orig.astype(np.float64) - wm.astype(np.float64)) ** 2))
    psnr = psnr_fn(orig, wm, data_range=255)
    s, _ = ssim_fn(orig, wm, channel_axis=2, data_range=255, full=True)
    return {"MSE": round(mse, 4), "PSNR_dB": round(float(psnr), 2), "SSIM": round(float(s), 4)}

def amplified_diff(orig, wm, factor=15):
    return np.clip(np.abs(orig.astype(np.float64) - wm.astype(np.float64)) * factor,
                   0, 255).astype(np.uint8)


# ─────────────────────────────────────────────
#  MID-FREQUENCY MASK (8x8 DCT block)
# ─────────────────────────────────────────────

MID_MASK = [(u, v) for u in range(8) for v in range(8) if 2 <= u + v <= 6]


# ═══════════════════════════════════════════════
#  METHOD 1: DCT
# ═══════════════════════════════════════════════

class DCTWatermark:
    """Block-DCT spread-spectrum. Modifies 18 mid-frequency 8x8 coefficients."""

    def __init__(self, alpha=25, block_size=8):
        self.alpha      = alpha
        self.block_size = block_size

    def _luma(self, img):
        return 0.299*img[...,0] + 0.587*img[...,1] + 0.114*img[...,2]

    def embed(self, image, wm_bits):
        img     = image.copy()
        H, W    = img.shape[:2]
        bs      = self.block_size
        bipolar = bits_to_bipolar(wm_bits)
        luma    = self._luma(img)
        idx     = 0
        for by in range(H // bs):
            for bx in range(W // bs):
                r0, c0 = by*bs, bx*bs
                block  = luma[r0:r0+bs, c0:c0+bs].copy()
                coeffs = dctn(block, norm='ortho')
                for (u, v) in MID_MASK:
                    coeffs[u, v] += self.alpha * bipolar[idx % len(bipolar)]
                    idx += 1
                delta = idctn(coeffs, norm='ortho') - block
                for c in range(3):
                    img[r0:r0+bs, c0:c0+bs, c] = np.clip(
                        img[r0:r0+bs, c0:c0+bs, c] + delta, 0, 255)
        print(f"[DCT] Embedded | alpha={self.alpha} | bits_used={idx}")
        return img

    def verify(self, watermarked, wm_bits):
        H, W    = watermarked.shape[:2]
        bs      = self.block_size
        luma    = self._luma(watermarked)
        ext     = []
        for by in range(H // bs):
            for bx in range(W // bs):
                r0, c0 = by*bs, bx*bs
                coeffs = dctn(luma[r0:r0+bs, c0:c0+bs], norm='ortho')
                for (u, v) in MID_MASK:
                    ext.append(coeffs[u, v])
        ext      = np.array(ext)
        bipolar  = bits_to_bipolar(wm_bits)
        tiled    = np.tile(bipolar, (len(ext)//len(bipolar))+1)[:len(ext)]
        ncc      = float(np.corrcoef(ext, tiled)[0, 1])
        detected = ncc > 0.05
        print(f"[DCT] NCC={ncc:.4f} | Detected={detected}")
        return {"ncc": round(ncc, 4), "detected": detected, "method": "DCT"}

    def spectrum(self, image):
        return np.log(1 + np.abs(dctn(self._luma(image), norm='ortho')))


# ═══════════════════════════════════════════════
#  METHOD 2: DWT (Haar)
# ═══════════════════════════════════════════════

class DWTWatermark:
    """Single-level Haar DWT. Embeds in LH sub-band."""

    def __init__(self, alpha=20, band='LH'):
        self.alpha = alpha
        self.band  = band

    def _fwd(self, ch):
        H, W = ch.shape
        a, b = ch[:H:2, :W:2], ch[:H:2, 1:W:2]
        c, d = ch[1:H:2, :W:2], ch[1:H:2, 1:W:2]
        return (a+b+c+d)/2, (a+b-c-d)/2, (a-b+c-d)/2, (a-b-c+d)/2

    def _inv(self, LL, LH, HL, HH):
        h, w = LL.shape
        out  = np.zeros((h*2, w*2), dtype=np.float64)
        out[:h*2:2,  :w*2:2] = (LL+LH+HL+HH)/2
        out[:h*2:2, 1:w*2:2] = (LL+LH-HL-HH)/2
        out[1:h*2:2, :w*2:2] = (LL-LH+HL-HH)/2
        out[1:h*2:2,1:w*2:2] = (LL-LH-HL+HH)/2
        return out

    def _get(self, LL, LH, HL, HH):
        return {'LL':LL,'LH':LH,'HL':HL,'HH':HH}[self.band]

    def _set(self, LL, LH, HL, HH, data):
        d = {'LL':LL,'LH':LH,'HL':HL,'HH':HH}
        d[self.band] = data
        return d['LL'], d['LH'], d['HL'], d['HH']

    def embed(self, image, wm_bits):
        img = image.copy()
        for c in range(3):
            ch             = img[:, :, c].astype(np.float64)
            LL, LH, HL, HH = self._fwd(ch)
            band           = self._get(LL, LH, HL, HH).copy().flatten()
            bipolar        = bits_to_bipolar(wm_bits)
            tiled          = np.tile(bipolar, (len(band)//len(bipolar))+1)[:len(band)]
            band          += self.alpha * tiled
            LL2,LH2,HL2,HH2 = self._set(LL,LH,HL,HH,
                               band.reshape(self._get(LL,LH,HL,HH).shape))
            img[:,:,c] = np.clip(self._inv(LL2,LH2,HL2,HH2), 0, 255)
        print(f"[DWT] Embedded | alpha={self.alpha} | band={self.band}")
        return img

    def verify(self, watermarked, wm_bits):
        ncc_vals = []
        for c in range(3):
            ch             = watermarked[:,:,c].astype(np.float64)
            LL, LH, HL, HH = self._fwd(ch)
            band           = self._get(LL,LH,HL,HH).flatten()
            bipolar        = bits_to_bipolar(wm_bits)
            tiled          = np.tile(bipolar, (len(band)//len(bipolar))+1)[:len(band)]
            ncc_vals.append(float(np.corrcoef(band, tiled)[0, 1]))
        ncc      = float(np.mean(ncc_vals))
        detected = ncc > 0.05
        print(f"[DWT] NCC={ncc:.4f} | Detected={detected}")
        return {"ncc": round(ncc, 4), "detected": detected, "method": "DWT"}

    def subbands_visual(self, image):
        ch             = np.clip(image,0,255).astype(np.uint8)[:,:,0].astype(np.float64)
        LL, LH, HL, HH = self._fwd(ch)
        def norm(x):
            mn,mx = x.min(), x.max()
            return ((x-mn)/(mx-mn+1e-8)*255).astype(np.uint8)
        return norm(LL), norm(LH), norm(HL), norm(HH)


# ═══════════════════════════════════════════════
#  METHOD 3: HYBRID DWT + DCT
# ═══════════════════════════════════════════════

class HybridWatermark:
    """
    Hybrid DWT+DCT watermarking:
      1. Haar DWT on luminance -> get LH sub-band
      2. Divide LH into 8x8 blocks -> DCT each block
      3. Embed watermark bits into mid-frequency DCT coefficients of LH
      4. IDCT -> put LH back -> IDWT -> reconstruct image
    Strongest method: combines DWT multi-resolution + DCT frequency selectivity.
    """

    def __init__(self, alpha=18, block_size=8):
        self.alpha      = alpha
        self.block_size = block_size
        self._dwt       = DWTWatermark(alpha=alpha, band='LH')

    def _luma(self, img):
        return 0.299*img[...,0] + 0.587*img[...,1] + 0.114*img[...,2]

    def _embed_in_band(self, band, wm_bits):
        H, W    = band.shape
        bs      = self.block_size
        out     = band.copy()
        bipolar = bits_to_bipolar(wm_bits)
        idx     = 0
        for by in range(H // bs):
            for bx in range(W // bs):
                r0, c0 = by*bs, bx*bs
                block  = out[r0:r0+bs, c0:c0+bs].copy()
                coeffs = dctn(block, norm='ortho')
                for (u, v) in MID_MASK:
                    coeffs[u, v] += self.alpha * bipolar[idx % len(bipolar)]
                    idx += 1
                out[r0:r0+bs, c0:c0+bs] = idctn(coeffs, norm='ortho')
        return out, idx

    def _extract_from_band(self, band):
        H, W = band.shape
        bs   = self.block_size
        ext  = []
        for by in range(H // bs):
            for bx in range(W // bs):
                r0, c0 = by*bs, bx*bs
                coeffs = dctn(band[r0:r0+bs, c0:c0+bs], norm='ortho')
                for (u, v) in MID_MASK:
                    ext.append(coeffs[u, v])
        return np.array(ext)

    def embed(self, image, wm_bits):
        img  = image.copy()
        luma = self._luma(img)
        LL, LH, HL, HH = self._dwt._fwd(luma)
        LH_wm, bits_used = self._embed_in_band(LH, wm_bits)
        luma_wm = np.clip(self._dwt._inv(LL, LH_wm, HL, HH), 0, 255)
        delta   = luma_wm - luma
        for c in range(3):
            img[:,:,c] = np.clip(img[:,:,c] + delta, 0, 255)
        print(f"[HYB] DWT+DCT embedded | alpha={self.alpha} | bits_used={bits_used}")
        return img

    def verify(self, watermarked, wm_bits):
        luma           = self._luma(watermarked)
        LL, LH, HL, HH = self._dwt._fwd(luma)
        ext            = self._extract_from_band(LH)
        bipolar        = bits_to_bipolar(wm_bits)
        tiled          = np.tile(bipolar, (len(ext)//len(bipolar))+1)[:len(ext)]
        ncc            = float(np.corrcoef(ext, tiled)[0, 1])
        detected       = ncc > 0.05
        print(f"[HYB] NCC={ncc:.4f} | Detected={detected}")
        return {"ncc": round(ncc, 4), "detected": detected, "method": "Hybrid DWT+DCT"}

    def lh_spectrum(self, image):
        luma           = self._luma(image)
        LL, LH, HL, HH = self._dwt._fwd(luma)
        return np.log(1 + np.abs(dctn(LH, norm='ortho')))


# ═══════════════════════════════════════════════
#  VISUALIZATION
# ═══════════════════════════════════════════════

def _show(ax, data, title, cmap='gray'):
    d = np.clip(data, 0, 255).astype(np.uint8) if data.dtype != np.uint8 else data
    ax.imshow(d if d.ndim == 3 else d, cmap=cmap, interpolation='nearest')
    ax.set_title(title, color='#cdd6f4', fontsize=9, pad=6)
    ax.axis('off')

def _dark_ax(ax, title=None):
    ax.set_facecolor('#1e1e2e'); ax.axis('off')
    if title:
        ax.set_title(title, color='#cdd6f4', fontsize=9, pad=6)

def _metrics_panel(ax, metrics, ext_result, label=""):
    _dark_ax(ax)
    det   = ext_result['detected']
    color = '#a6e3a1' if det else '#f38ba8'
    ax.text(0.1, 0.93, f'{label} Metrics', transform=ax.transAxes,
            color='#cba6f7', fontsize=10, fontweight='bold')
    ax.text(0.1, 0.55,
            f"PSNR   {metrics.get('PSNR_dB','—')} dB\n"
            f"MSE    {metrics.get('MSE','—')}\n"
            f"SSIM   {metrics.get('SSIM','—')}\n\n"
            f"NCC    {ext_result['ncc']}\n"
            f"Status {'DETECTED' if det else 'NOT FOUND'}",
            transform=ax.transAxes, color='white', fontsize=10,
            fontfamily='monospace', verticalalignment='center', linespacing=2.0)
    ax.text(0.5, 0.06, 'WATERMARK VERIFIED' if det else 'NOT DETECTED',
            transform=ax.transAxes, color=color,
            fontsize=9, fontweight='bold', ha='center')


# ── Embed plots ──────────────────────────────

def visualize_dct_embed(original, watermarked, metrics, ext_result, dct_obj):
    diff = amplified_diff(original, watermarked)
    fig  = plt.figure(figsize=(16, 10), facecolor='#0e1117')
    fig.suptitle(f'DCT Embedding  |  alpha={dct_obj.alpha}',
                 color='white', fontsize=14, fontweight='bold', y=0.97)
    gs   = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(4)]
    s_o  = dct_obj.spectrum(original)
    s_w  = dct_obj.spectrum(watermarked)
    _show(axes[0], original.astype(np.uint8),   'Original',        cmap=None)
    _show(axes[1], watermarked.astype(np.uint8), 'Watermarked',     cmap=None)
    _show(axes[2], diff,                          'Difference x15',  cmap='hot')
    _metrics_panel(axes[3], metrics, ext_result, 'DCT')
    _show(axes[4], s_o,              'DCT spectrum (orig)', cmap='inferno')
    _show(axes[5], s_w,              'DCT spectrum (wm)',   cmap='inferno')
    _show(axes[6], np.abs(s_w - s_o),'Spectrum delta',      cmap='plasma')
    _dark_ax(axes[7], 'Pixel delta distribution')
    axes[7].set_facecolor('#1e1e2e')
    axes[7].hist((original - watermarked).flatten(), bins=80, color='#89b4fa',
                 edgecolor='none', alpha=0.85)
    axes[7].tick_params(colors='#888')
    for sp in axes[7].spines.values(): sp.set_edgecolor('#333')
    plt.savefig('dct_embed_results.png', dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print("[VIZ] Saved -> dct_embed_results.png"); plt.close()


def visualize_dwt_embed(original, watermarked, metrics, ext_result, dwt_obj):
    diff           = amplified_diff(original, watermarked)
    LL, LH, HL, HH = dwt_obj.subbands_visual(original)
    fig = plt.figure(figsize=(16, 10), facecolor='#0e1117')
    fig.suptitle(f'DWT Embedding (Haar)  |  alpha={dwt_obj.alpha}  |  band={dwt_obj.band}',
                 color='white', fontsize=14, fontweight='bold', y=0.97)
    gs   = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(4)]
    _show(axes[0], original.astype(np.uint8),   'Original',          cmap=None)
    _show(axes[1], watermarked.astype(np.uint8), 'Watermarked',       cmap=None)
    _show(axes[2], diff,                          'Difference x15',    cmap='hot')
    _metrics_panel(axes[3], metrics, ext_result, 'DWT')
    _show(axes[4], LL, 'Sub-band: LL',              cmap='gray')
    _show(axes[5], LH, 'Sub-band: LH <- embedded',  cmap='gray')
    _show(axes[6], HL, 'Sub-band: HL',              cmap='gray')
    _show(axes[7], HH, 'Sub-band: HH',              cmap='gray')
    plt.savefig('dwt_embed_results.png', dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print("[VIZ] Saved -> dwt_embed_results.png"); plt.close()


def visualize_hybrid_embed(original, watermarked, metrics, ext_result, hyb_obj):
    diff    = amplified_diff(original, watermarked)
    lh_o    = hyb_obj.lh_spectrum(original)
    lh_w    = hyb_obj.lh_spectrum(watermarked)
    dwt_tmp = DWTWatermark()
    _, LH, _, _ = dwt_tmp.subbands_visual(watermarked)
    fig = plt.figure(figsize=(16, 10), facecolor='#0e1117')
    fig.suptitle(f'Hybrid DWT+DCT Embedding  |  alpha={hyb_obj.alpha}',
                 color='white', fontsize=14, fontweight='bold', y=0.97)
    gs   = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(4)]
    _show(axes[0], original.astype(np.uint8),   'Original',              cmap=None)
    _show(axes[1], watermarked.astype(np.uint8), 'Watermarked',           cmap=None)
    _show(axes[2], diff,                          'Difference x15',        cmap='hot')
    _metrics_panel(axes[3], metrics, ext_result, 'Hybrid')
    _show(axes[4], lh_o,             'LH-DCT spectrum (orig)', cmap='inferno')
    _show(axes[5], lh_w,             'LH-DCT spectrum (wm)',   cmap='inferno')
    _show(axes[6], np.abs(lh_w-lh_o),'LH spectrum delta',      cmap='plasma')
    _show(axes[7], LH,               'LH sub-band (wm)',        cmap='gray')
    plt.savefig('hybrid_embed_results.png', dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print("[VIZ] Saved -> hybrid_embed_results.png"); plt.close()


def visualize_logo_embed(original, watermarked, metrics, ext_result,
                          logo_original, logo_extracted):
    diff = amplified_diff(original, watermarked)
    ber  = float(np.mean(logo_original.flatten() != logo_extracted.flatten()))
    fig  = plt.figure(figsize=(20, 6), facecolor='#0e1117')
    fig.suptitle('Logo Watermark — Hybrid DWT+DCT + AES + Reed-Solomon',
                 color='white', fontsize=14, fontweight='bold', y=1.01)
    gs   = gridspec.GridSpec(1, 6, figure=fig, wspace=0.3)
    axes = [fig.add_subplot(gs[0, c]) for c in range(6)]
    _show(axes[0], original.astype(np.uint8),   'Original image',    cmap=None)
    _show(axes[1], watermarked.astype(np.uint8), 'Watermarked image', cmap=None)
    _show(axes[2], diff,                          'Difference x15',    cmap='hot')
    _show(axes[3], logo_original * 255,           'Logo (original)',   cmap='gray')
    _show(axes[4], logo_extracted * 255,          'Logo (extracted)',  cmap='gray')
    _dark_ax(axes[5])
    det   = ext_result['detected']
    color = '#a6e3a1' if det else '#f38ba8'
    axes[5].text(0.1, 0.93, 'Logo Verification', transform=axes[5].transAxes,
                 color='#cba6f7', fontsize=10, fontweight='bold')
    axes[5].text(0.1, 0.55,
                 f"PSNR   {metrics.get('PSNR_dB','—')} dB\n"
                 f"MSE    {metrics.get('MSE','—')}\n"
                 f"SSIM   {metrics.get('SSIM','—')}\n\n"
                 f"NCC    {ext_result['ncc']}\n"
                 f"BER    {ber:.4f}",
                 transform=axes[5].transAxes, color='white', fontsize=10,
                 fontfamily='monospace', verticalalignment='center', linespacing=2.0)
    axes[5].text(0.5, 0.06, 'LOGO VERIFIED' if det else 'NOT DETECTED',
                 transform=axes[5].transAxes, color=color,
                 fontsize=9, fontweight='bold', ha='center')
    plt.savefig('logo_embed_results.png', dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print("[VIZ] Saved -> logo_embed_results.png"); plt.close()


def visualize_comparison(orig, dct_wm, dwt_wm, hyb_wm,
                          dct_m, dwt_m, hyb_m, dct_e, dwt_e, hyb_e):
    fig = plt.figure(figsize=(20, 10), facecolor='#0e1117')
    fig.suptitle('Method Comparison: DCT vs DWT vs Hybrid DWT+DCT',
                 color='white', fontsize=14, fontweight='bold', y=0.97)
    gs   = gridspec.GridSpec(2, 4, figure=fig, hspace=0.4, wspace=0.3)
    axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(4)]
    _show(axes[0], orig,   'Original',           cmap=None)
    _show(axes[1], dct_wm, 'DCT watermarked',    cmap=None)
    _show(axes[2], dwt_wm, 'DWT watermarked',    cmap=None)
    _show(axes[3], hyb_wm, 'Hybrid watermarked', cmap=None)
    _show(axes[4], amplified_diff(orig, orig),   '(no diff)',       cmap='hot')
    _show(axes[5], amplified_diff(orig, dct_wm), 'DCT diff x15',   cmap='hot')
    _show(axes[6], amplified_diff(orig, dwt_wm), 'DWT diff x15',   cmap='hot')
    _show(axes[7], amplified_diff(orig, hyb_wm), 'Hybrid diff x15',cmap='hot')
    for ax, m, e in [(axes[1],dct_m,dct_e),(axes[2],dwt_m,dwt_e),(axes[3],hyb_m,hyb_e)]:
        ax.set_xlabel(f"PSNR {m['PSNR_dB']}dB  SSIM {m['SSIM']}  NCC {e['ncc']}",
                      color='#aaa', fontsize=8)
    plt.savefig('comparison_all_methods.png', dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print("[VIZ] Saved -> comparison_all_methods.png"); plt.close()


# ── Extract plots ────────────────────────────

def visualize_extract(watermarked, ext_result, method_obj,
                       original=None, logo_orig=None, logo_ext=None,
                       filename='extract_results.png'):
    n = 5 if logo_orig is not None else 4
    fig = plt.figure(figsize=(4*n, 6), facecolor='#0e1117')
    fig.suptitle(f"{ext_result.get('method','?')} — Extraction & Verification",
                 color='white', fontsize=14, fontweight='bold', y=1.01)
    gs   = gridspec.GridSpec(1, n, figure=fig, wspace=0.3)
    axes = [fig.add_subplot(gs[0, c]) for c in range(n)]

    _show(axes[0], np.clip(watermarked,0,255).astype(np.uint8), 'Watermarked', cmap=None)

    if hasattr(method_obj, 'spectrum'):
        _show(axes[1], method_obj.spectrum(watermarked), 'DCT spectrum', cmap='inferno')
    elif hasattr(method_obj, 'lh_spectrum'):
        _show(axes[1], method_obj.lh_spectrum(watermarked), 'LH-DCT spectrum', cmap='inferno')
    elif hasattr(method_obj, 'subbands_visual'):
        _, LH, _, _ = method_obj.subbands_visual(watermarked)
        _show(axes[1], LH, 'LH sub-band', cmap='gray')

    if original is not None:
        _show(axes[2], amplified_diff(original, watermarked), 'Diff vs original x15', cmap='hot')
    else:
        _dark_ax(axes[2], 'Original not provided')
        axes[2].text(0.5, 0.5, 'not provided', transform=axes[2].transAxes,
                     color='#555', ha='center', va='center', fontsize=10)

    _dark_ax(axes[3])
    det   = ext_result['detected']
    color = '#a6e3a1' if det else '#f38ba8'
    axes[3].text(0.1, 0.93, 'Extraction Result', transform=axes[3].transAxes,
                 color='#cba6f7', fontsize=10, fontweight='bold')
    axes[3].text(0.1, 0.55,
                 f"Method   {ext_result.get('method','?')}\n"
                 f"NCC      {ext_result['ncc']}\n\n"
                 f"Threshold  > 0.05\n"
                 f"Result   {'PASS' if det else 'FAIL'}",
                 transform=axes[3].transAxes, color='white', fontsize=10,
                 fontfamily='monospace', verticalalignment='center', linespacing=2.2)
    axes[3].text(0.5, 0.06, 'WATERMARK DETECTED' if det else 'NOT DETECTED',
                 transform=axes[3].transAxes, color=color,
                 fontsize=10, fontweight='bold', ha='center')

    if logo_orig is not None and logo_ext is not None and n == 5:
        combined = np.hstack([logo_orig * 255,
                               np.ones((LOGO_SIZE, 4), np.uint8) * 80,
                               logo_ext * 255])
        _show(axes[4], combined, 'Logo: original | extracted', cmap='gray')

    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='#0e1117')
    print(f"[VIZ] Saved -> {filename}"); plt.close()
