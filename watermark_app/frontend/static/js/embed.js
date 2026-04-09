/* embed.js — Handles the watermark embedding page */

let currentWmType = 'text';

/* ── Type Toggle ─────────────────────────── */

function switchType(type) {
  currentWmType = type;
  document.getElementById('text-section').style.display = type === 'text' ? '' : 'none';
  document.getElementById('logo-section').style.display = type === 'logo' ? '' : 'none';
  document.getElementById('tab-text').classList.toggle('active', type === 'text');
  document.getElementById('tab-logo').classList.toggle('active', type === 'logo');
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
  const dt = e.dataTransfer;
  if (dt.files.length) {
    input.files = dt.files;
    const previewId  = inputId === 'embed-image' ? 'img-preview'   : 'logo-preview';
    const fnameId    = inputId === 'embed-image' ? 'img-fname'      : 'logo-fname';
    previewFile(input, previewId, fnameId);
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
  t._timer = setTimeout(() => t.classList.remove('show'), 4000);
}

/* ── Loading ─────────────────────────────── */

function setLoading(on) {
  document.getElementById('embed-btn').disabled    = on;
  document.getElementById('embed-spinner').classList.toggle('visible', on);
}

/* ── Main Embed Call ─────────────────────── */

async function runEmbed() {
  const password = document.getElementById('embed-password').value.trim();
  const imageFile = document.getElementById('embed-image').files[0];
  const method = document.querySelector('input[name="method"]:checked')?.value || 'HYBRID';

  /* Validation */
  if (!password)   { showToast('⚠️ Please enter a password.', 'error'); return; }
  if (!imageFile)  { showToast('⚠️ Please upload a cover image.', 'error'); return; }

  if (currentWmType === 'text') {
    const txt = document.getElementById('embed-text').value.trim();
    if (!txt) { showToast('⚠️ Please enter watermark text.', 'error'); return; }
  } else {
    const logo = document.getElementById('embed-logo').files[0];
    if (!logo) { showToast('⚠️ Please upload a logo image.', 'error'); return; }
  }

  setLoading(true);
  showToast(`⏳ Embedding with ${method}…`, 'info');

  const form = new FormData();
  form.append('password',   password);
  form.append('method',     method);
  form.append('wm_type',    currentWmType);
  form.append('image',      imageFile);

  if (currentWmType === 'text') {
    form.append('watermark_text', document.getElementById('embed-text').value.trim());
  } else {
    form.append('logo', document.getElementById('embed-logo').files[0]);
  }

  try {
    const res  = await fetch('/api/embed', { method: 'POST', body: form });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(`❌ ${data.error || 'Server error'}`, 'error');
      setLoading(false);
      return;
    }

    renderResult(data);
    showToast('✅ Watermark embedded successfully!', 'success');

  } catch (err) {
    showToast('❌ Network error — is the server running?', 'error');
    console.error(err);
  } finally {
    setLoading(false);
  }
}

/* ── Render Result ───────────────────────── */

function renderResult(data) {
  /* Show result panel */
  document.getElementById('result-placeholder').style.display = 'none';
  const rc = document.getElementById('result-content');
  rc.classList.add('visible');

  /* Image */
  document.getElementById('result-image').src = `data:image/png;base64,${data.watermarked_b64}`;

  /* Method badge */
  document.getElementById('result-method-badge').textContent = data.method;

  /* Metrics row */
  const mr = document.getElementById('metrics-row');
  const m  = data.metrics || {};
  mr.innerHTML = [
    ['PSNR',  (m.PSNR_dB || '—') + ' dB'],
    ['MSE',   m.MSE ?? '—'],
    ['SSIM',  m.SSIM ?? '—'],
    ['NCC',   data.ncc ?? '—'],
  ].map(([label, val]) => `
    <div class="metric-chip">
      <span class="metric-label">${label}</span>
      <span class="metric-value">${val}</span>
    </div>`).join('');

  /* NCC inline */
  document.getElementById('ncc-val').textContent = data.ncc ?? '—';
}
