const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const apiKeyInput = document.getElementById('apiKeyInput');
const statusSection = document.getElementById('statusSection');
const statusText = document.getElementById('statusText');
const resultSection = document.getElementById('resultSection');
const resultTable = document.getElementById('resultTable');
const errorSection = document.getElementById('errorSection');
const errorText = document.getElementById('errorText');
const downloadCsvBtn = document.getElementById('downloadCsvBtn');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');

let currentJobId = null;

// ── Upload Zone ──────────────────────────────────────────

uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('dragover');
  const files = e.dataTransfer.files;
  if (files.length) handleFile(files[0]);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});

// ── Upload & Poll ────────────────────────────────────────

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    return alert('只支持 PDF 文件');
  }

  const apiKey = apiKeyInput.value.trim() || 'dev-key-123';
  hideAll();

  const formData = new FormData();
  formData.append('file', file);

  statusSection.hidden = false;
  statusText.textContent = '上传中...';

  try {
    const uploadRes = await fetch('/api/upload', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${apiKey}` },
      body: formData,
    });
    if (!uploadRes.ok) {
      const err = await uploadRes.json();
      return showError(err.detail || '上传失败');
    }
    const { job_id } = await uploadRes.json();
    currentJobId = job_id;
    pollJob(job_id);
  } catch (err) {
    showError('网络错误: ' + err.message);
  }
}

async function pollJob(jobId) {
  statusText.textContent = '正在处理...';
  const maxAttempts = 120;
  for (let i = 0; i < maxAttempts; i++) {
    await sleep(2000);
    try {
      const res = await fetch(`/api/job/${jobId}`);
      const job = await res.json();
      if (job.status === 'completed') {
        statusSection.hidden = true;
        return showResult(jobId);
      }
      if (job.status === 'failed') {
        statusSection.hidden = true;
        return showError(job.error || '处理失败');
      }
    } catch {
      // retry
    }
  }
  statusSection.hidden = true;
  showError('处理超时，请重试');
}

async function showResult(jobId) {
  const res = await fetch(`/api/job/${jobId}/result`);
  const { data } = await res.json();
  if (!data) return showError('无结果数据');

  resultSection.hidden = false;
  const flat = flattenDict(data);
  let html = '<table><thead><tr>';
  for (const key of Object.keys(flat)) {
    html += `<th>${escapeHtml(key)}</th>`;
  }
  html += '</tr></thead><tbody><tr>';
  for (const val of Object.values(flat)) {
    html += `<td>${escapeHtml(String(val))}</td>`;
  }
  html += '</tr></tbody></table>';
  resultTable.innerHTML = html;

  downloadCsvBtn.onclick = () => downloadResult(jobId, 'csv');
  downloadJsonBtn.onclick = () => downloadResult(jobId, 'json');
}

// ── Download ──────────────────────────────────────────────

async function downloadResult(jobId, fmt) {
  const apiKey = apiKeyInput.value.trim() || 'dev-key-123';
  const res = await fetch(`/api/job/${jobId}/download/${fmt}`, {
    headers: { 'Authorization': `Bearer ${apiKey}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return alert(err.detail || '下载失败');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${jobId}.${fmt}`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Helpers ──────────────────────────────────────────────

function hideAll() {
  statusSection.hidden = true;
  resultSection.hidden = true;
  errorSection.hidden = true;
}

function showError(msg) {
  errorSection.hidden = false;
  errorText.textContent = msg;
}

function flattenDict(d, prefix = '', sep = '_') {
  let result = {};
  for (const [k, v] of Object.entries(d)) {
    const key = prefix ? prefix + sep + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(result, flattenDict(v, key, sep));
    } else if (Array.isArray(v)) {
      result[key] = v.join('; ');
    } else {
      result[key] = v == null ? '' : v;
    }
  }
  return result;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
