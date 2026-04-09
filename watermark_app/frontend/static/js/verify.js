/* verify.js — Handles the watermark verification page */

let currentVType = 'text';

/* ── Type Toggle ─────────────────────────── */

function switchVType(type) {
  currentVType = type;
  document.getElementById('vtext-section').style.display = type === 'text' ? '' : 'none';
  document.getElementById('vlogo-section').style.display = type === 'logo' ? '' : 'none';
  document.getElementById('vtab-text').classList.toggle('active', type === 'text');
  document.getElementById('vtab-logo').classList.toggle('active', type === 'logo');
}

/* ── Drop Zone Helpers ───────────────────── */

function dragOver(e, zoneId) {
  e.preventDefault();
  document.getElementById(zoneId).classList.add('drag-over');
}

function dragLeave(zoneId) {
  document.getElementById(zoneId).classList.remove('drag-over');
}

function dropFile(e, inputId, zoneId) {
  e.preventDefault();
  dragLeave(zoneId);
  const input = document.getElementById(inputId);
  if (e.dataTransfer.files.length) {
    input.files = e.dataTransfer.files;
    const map = {
      'verify-image': ['vimg-preview', 'vimg-fname'],
      'verify-logo':  ['vlogo-preview', 'vlogo-fname'],
    };
    const [pId, fId] = map[inputId] || [];
    if (pId) previewFile(input, pId, fId);
  }
}

function previewFile(input, previewId, fnameId) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById(fnameId).textContent = file.name;
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById(previewId);
    img.src = e.target.result;
    img.style.display = 'block';
    /* Also show in result preview area */
    if (input.id === 'verify-image') {
      document.getElementById('vresult-image').src = e.target.result;
    }
  };
  reader.readAsDataURL(file);
}

/* ── Password Toggle ─────────────────────── */

function togglePwd(inputId, btn) {
  const inp = document.getElementById(inputId);
  if (inp.type === 'password') {
    inp.type = 'text';
    btn.textContent = '🙈';
  } else {
    inp.type = 'password';
    btn.textContent = '👁️';
  }
}

/* ── Toast ───────────────────────────────── */

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 5000);
}

/* ── Loading ─────────────────────────────── */

function setLoading(on) {
  document.getElementById('verify-btn').disabled = on;
  document.getElementById('verify-spinner').classList.toggle('visible', on);
}

/* ── Main Verify Call ────────────────────── */

async function runVerify() {
  const password  = document.getElementById('verify-password').value.trim();
  const imageFile = document.getElementById('verify-image').files[0];
  const method    = document.querySelector('input[name="vmethod"]:checked')?.value || 'HYBRID';

  if (!password)  { showToast('⚠️ Please enter a password.', 'error'); return; }
  if (!imageFile) { showToast('⚠️ Please upload a watermarked image.', 'error'); return; }

  if (currentVType === 'text') {
    const txt = document.getElementById('verify-text').value.trim();
    if (!txt) { showToast('⚠️ Please enter the watermark text.', 'error'); return; }
  } else {
    const logo = document.getElementById('verify-logo').files[0];
    if (!logo) { showToast('⚠️ Please upload the original logo.', 'error'); return; }
  }

  setLoading(true);
  showToast(`⏳ Running ${method} verification…`, 'info');

  const form = new FormData();
  form.append('password', password);
  form.append('method',   method);
  form.append('wm_type',  currentVType);
  form.append('image',    imageFile);

  if (currentVType === 'text') {
    form.append('watermark_text', document.getElementById('verify-text').value.trim());
  } else {
    form.append('logo', document.getElementById('verify-logo').files[0]);
  }

  try {
    const res  = await fetch('/api/verify', { method: 'POST', body: form });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(`❌ ${data.error || 'Server error'}`, 'error');
      setLoading(false);
      return;
    }

    renderVerifyResult(data);
    showToast(data.detected ? '✅ Watermark verified!' : '❌ Watermark NOT detected.', data.detected ? 'success' : 'error');

  } catch (err) {
    showToast('❌ Network error — is the server running?', 'error');
    console.error(err);
  } finally {
    setLoading(false);
  }
}

/* ── Render Result ───────────────────────── */

function renderVerifyResult(data) {
  /* Show result panel */
  document.getElementById('vresult-placeholder').style.display = 'none';
  const rc = document.getElementById('vresult-content');
  rc.classList.add('visible');

  /* Method badge */
  document.getElementById('vresult-method-badge').textContent = data.method;

  /* Status box */
  const box   = document.getElementById('vstatus-box');
  const icon  = document.getElementById('vstatus-icon');
  const title = document.getElementById('vstatus-title');
  const desc  = document.getElementById('vstatus-desc');

  box.className = 'verify-status ' + (data.detected ? 'verified' : 'rejected');

  if (data.detected) {
    icon.textContent  = '✅';
    title.textContent = 'Watermark Verified';
    desc.textContent  = `The ${data.method} watermark was detected. NCC ${data.ncc} > threshold ${data.threshold}.`;
  } else {
    icon.textContent  = '❌';
    title.textContent = 'Not Detected';
    desc.textContent  = `No matching watermark found. NCC ${data.ncc} ≤ threshold ${data.threshold}. Wrong password, method, or image?`;
  }

  /* NCC bar */
  const ncc     = Math.max(0, Math.min(1, data.ncc ?? 0));
  const pct     = (ncc * 100).toFixed(1);
  document.getElementById('vncc-val').textContent    = data.ncc ?? '—';
  document.getElementById('vncc-fill').style.width   = pct + '%';
  document.getElementById('vncc-fill').style.background =
    data.detected
      ? 'linear-gradient(90deg, var(--accent-green), #00a06b)'
      : 'linear-gradient(90deg, var(--accent-red), #c02040)';

  /* Detail row */
  const dbox = document.getElementById('vdetail-box');
  dbox.style.display = '';
  document.getElementById('vdetail-method').textContent = data.method;
  document.getElementById('vdetail-ncc').textContent    = data.ncc;

  /* Extracted logo */
  const logoCompare = document.getElementById('logo-compare');
  if (data.extracted_logo_b64) {
    document.getElementById('extracted-logo-img').src = `data:image/png;base64,${data.extracted_logo_b64}`;
    logoCompare.style.display = '';
  } else {
    logoCompare.style.display = 'none';
  }
}
