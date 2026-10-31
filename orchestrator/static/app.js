/**
 * WolfBox UI — Shared Helpers
 * API client with graceful error toasts, offline markdown renderer, and DeskLight hooks
 */

// --- Toast Notifications ---
function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'error' ? '⚠️ ' : type === 'success' ? '✓ ' : type === 'warning' ? '⚡ ' : 'ℹ️ ';
  toast.textContent = `${icon}${message}`;

  toast.addEventListener('click', () => {
    toast.remove();
  });

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// --- API Client ---
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      const text = await res.text();
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const errorMsg = (data && (data.error || data.detail)) || `Request failed (${res.status})`;
      console.warn(`API error on ${url}:`, errorMsg);
      showToast(errorMsg, 'error');
      return { ok: false, error: errorMsg, status: res.status, data };
    }

    return { ok: true, data, status: res.status };
  } catch (err) {
    const errorMsg = err.message || 'Network connection error';
    console.warn(`Network failure on ${url}:`, err);
    showToast(`API unreachable: ${errorMsg}`, 'warning');
    return { ok: false, error: errorMsg, status: 0 };
  }
}

// --- Simple Offline Markdown Renderer ---
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderMarkdown(md) {
  if (!md) return '';

  const lines = String(md).split('\n');
  let html = '';
  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBuffer = [];
  let inList = false;
  let listType = null; // 'ul' or 'ol'

  function closeList() {
    if (inList) {
      html += `</${listType}>\n`;
      inList = false;
      listType = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced code blocks
    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        html += `<pre><code>${codeBuffer.join('\n')}</code></pre>\n`;
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        closeList();
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(escapeHtml(line));
      continue;
    }

    const trimmed = line.trim();

    if (!trimmed) {
      closeList();
      continue;
    }

    // Headings
    if (trimmed.startsWith('# ')) {
      closeList();
      html += `<h1>${parseInline(escapeHtml(trimmed.slice(2)))}</h1>\n`;
      continue;
    }
    if (trimmed.startsWith('## ')) {
      closeList();
      html += `<h2>${parseInline(escapeHtml(trimmed.slice(3)))}</h2>\n`;
      continue;
    }
    if (trimmed.startsWith('### ')) {
      closeList();
      html += `<h3>${parseInline(escapeHtml(trimmed.slice(4)))}</h3>\n`;
      continue;
    }
    if (trimmed.startsWith('#### ')) {
      closeList();
      html += `<h4>${parseInline(escapeHtml(trimmed.slice(5)))}</h4>\n`;
      continue;
    }

    // Blockquote
    if (trimmed.startsWith('> ')) {
      closeList();
      html += `<blockquote>${parseInline(escapeHtml(trimmed.slice(2)))}</blockquote>\n`;
      continue;
    }

    // Unordered List
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList || listType !== 'ul') {
        closeList();
        inList = true;
        listType = 'ul';
        html += `<ul>\n`;
      }
      html += `<li>${parseInline(escapeHtml(trimmed.slice(2)))}</li>\n`;
      continue;
    }

    // Ordered List
    const olMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        closeList();
        inList = true;
        listType = 'ol';
        html += `<ol>\n`;
      }
      html += `<li>${parseInline(escapeHtml(olMatch[2]))}</li>\n`;
      continue;
    }

    // Regular paragraph
    closeList();
    html += `<p>${parseInline(escapeHtml(line))}</p>\n`;
  }

  if (inCodeBlock) {
    html += `<pre><code>${codeBuffer.join('\n')}</code></pre>\n`;
  }
  closeList();

  return html;
}

function parseInline(text) {
  if (!text) return '';
  // Inline code: `code`
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold: **text** or __text__
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  // Italic: *text* or _text_
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  text = text.replace(/(^|[^A-Za-z0-9_])_([^_]+)_(?![A-Za-z0-9_])/g, '$1<em>$2</em>');
  return text;
}

// --- Desk Light Driver Hooks (defensive WS7 integration) ---
const DeskLightHelper = {
  isSupported() {
    if (window.DeskLight && typeof window.DeskLight.supported === 'function') {
      try { return Boolean(window.DeskLight.supported()); } catch { return false; }
    }
    if (typeof window.deskLightSupported === 'function') {
      try { return Boolean(window.deskLightSupported()); } catch { return false; }
    }
    return false;
  },

  async connect() {
    if (window.DeskLight && typeof window.DeskLight.connect === 'function') {
      return await window.DeskLight.connect();
    }
    if (typeof window.connectDeskLight === 'function') {
      return await window.connectDeskLight();
    }
    showToast('Web Serial not supported in this browser', 'warning');
    return false;
  },

  isConnected() {
    if (window.DeskLight && typeof window.DeskLight.isConnected === 'function') {
      return window.DeskLight.isConnected();
    }
    return false;
  },

  setState(state) {
    console.log(`[DeskLight] setState: ${state}`);
    if (window.DeskLight && typeof window.DeskLight.setState === 'function') {
      try { window.DeskLight.setState(state); } catch (e) { console.warn(e); }
    } else if (typeof window.setDeskState === 'function') {
      try { window.setDeskState(state); } catch (e) { console.warn(e); }
    }
  },

  flash(n = 3) {
    console.log(`[DeskLight] flash: ${n}`);
    if (window.DeskLight && typeof window.DeskLight.flash === 'function') {
      try { window.DeskLight.flash(n); } catch (e) { console.warn(e); }
    } else if (typeof window.flashDesk === 'function') {
      try { window.flashDesk(n); } catch (e) { console.warn(e); }
    }
  }
};

// --- Formatters ---
function formatIsoDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

// --- Tabs Utility ---
function setupTabs() {
  const buttons = document.querySelectorAll('.tab-btn[data-tab]');
  const show = (btn) => {
    buttons.forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-content').forEach(c =>
      c.classList.toggle('active', c.id === btn.getAttribute('data-tab')));
  };
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      show(btn);
      history.replaceState(null, '', '#' + btn.getAttribute('data-tab'));
    });
    // Deep link: student.html?id=alex#tab-plan opens that tab.
    if (location.hash === '#' + btn.getAttribute('data-tab')) show(btn);
  });
}

// --- Expose on window ---
if (typeof window !== 'undefined') {
  window.showToast = showToast;
  window.apiFetch = apiFetch;
  window.renderMarkdown = renderMarkdown;
  window.escapeHtml = escapeHtml;
  window.formatIsoDate = formatIsoDate;
  window.setupTabs = setupTabs;
  window.DeskLightHelper = DeskLightHelper;
}


