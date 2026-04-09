# WatermarkShield — Digital Image Watermarking Dashboard

## Project Structure

```
watermark_app/
├── backend/
│   ├── app.py                 ← Flask app + API routes
│   ├── watermark_service.py   ← Business logic (embed/verify)
│   └── watermark_core.py      ← Core algorithms (DCT, DWT, Hybrid, AES, RS)
├── frontend/
│   ├── templates/
│   │   ├── index.html         ← Home page
│   │   ├── embed.html         ← Embed watermark page
│   │   └── verify.html        ← Verify watermark page
│   └── static/
│       ├── css/
│       │   └── style.css      ← Dark theme stylesheet
│       └── js/
│           ├── embed.js       ← Embed page logic
│           └── verify.js      ← Verify page logic
├── requirements.txt
└── README.md
```

## Setup & Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the server

```bash
cd backend
python app.py
```

### 3. Open in browser

```
http://localhost:5000
```

---

## Features

| Feature             | Detail                                       |
|---------------------|----------------------------------------------|
| Encryption          | AES-256-CTR via PBKDF2 key derivation        |
| Error Correction    | Reed-Solomon ECC (10 ECC bytes per block)    |
| Embed Methods       | DCT · DWT (Haar) · Hybrid DWT+DCT           |
| Watermark Types     | Text (UTF-8) · Binary Logo (32×32)           |
| Metrics             | PSNR · MSE · SSIM · NCC                     |
| Verification        | NCC correlation threshold > 0.05             |

## API Endpoints

| Method | Path           | Description                      |
|--------|----------------|----------------------------------|
| GET    | `/`            | Home page                        |
| GET    | `/embed`       | Embed watermark page             |
| GET    | `/verify`      | Verify watermark page            |
| POST   | `/api/embed`   | Embed watermark (returns base64) |
| GET    | `/api/download`| Download last watermarked PNG    |
| POST   | `/api/verify`  | Verify watermark (returns NCC)   |

### POST /api/embed

Form fields:
- `image`          — cover image file
- `password`       — AES password
- `wm_type`        — `text` or `logo`
- `watermark_text` — (if text) the text to embed
- `logo`           — (if logo) logo image file
- `method`         — `DCT`, `DWT`, or `HYBRID`

### POST /api/verify

Same fields as embed. Returns:
```json
{
  "detected": true,
  "ncc": 0.312,
  "method": "HYBRID",
  "threshold": 0.05
}
```
