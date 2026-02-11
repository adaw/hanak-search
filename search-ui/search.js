/**
 * Hanak Search — Masterpiece typeahead search overlay
 * Injects into any page. Activates on magnifying glass click or Ctrl+K.
 */
(function() {
  'use strict';

  const API_BASE = '/api';
  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 150;
  const MAX_SUGGESTIONS = 8;

  let overlay = null;
  let input = null;
  let resultsList = null;
  let activeIndex = -1;
  let debounceTimer = null;
  let isOpen = false;

  // ─── Create DOM ───────────────────────────────────────
  function createOverlay() {
    overlay = document.createElement('div');
    overlay.id = 'hanak-search-overlay';
    overlay.innerHTML = `
      <div class="hs-backdrop"></div>
      <div class="hs-modal">
        <div class="hs-input-wrap">
          <svg class="hs-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <input type="text" class="hs-input" placeholder="Hledejte produkty, kolekce, inspirace..." autocomplete="off" spellcheck="false">
          <kbd class="hs-kbd">ESC</kbd>
        </div>
        <div class="hs-results">
          <div class="hs-empty">Začněte psát pro vyhledávání...</div>
        </div>
        <div class="hs-footer">
          <span class="hs-footer-hint">
            <kbd>↑↓</kbd> navigace &nbsp; <kbd>Enter</kbd> otevřít &nbsp; <kbd>Esc</kbd> zavřít
          </span>
          <span class="hs-footer-time"></span>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    input = overlay.querySelector('.hs-input');
    resultsList = overlay.querySelector('.hs-results');

    // Events
    overlay.querySelector('.hs-backdrop').addEventListener('click', close);
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);
  }

  // ─── Open / Close ─────────────────────────────────────
  function open() {
    if (!overlay) createOverlay();
    isOpen = true;
    overlay.classList.add('hs-active');
    input.value = '';
    resultsList.innerHTML = '<div class="hs-empty">Začněte psát pro vyhledávání...</div>';
    activeIndex = -1;
    requestAnimationFrame(() => input.focus());
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    overlay.classList.remove('hs-active');
    document.body.style.overflow = '';
  }

  // ─── Input handling ───────────────────────────────────
  function onInput() {
    clearTimeout(debounceTimer);
    const q = input.value.trim();

    if (q.length < MIN_CHARS) {
      resultsList.innerHTML = '<div class="hs-empty">Začněte psát pro vyhledávání...</div>';
      activeIndex = -1;
      return;
    }

    resultsList.innerHTML = '<div class="hs-loading"><div class="hs-spinner"></div></div>';
    debounceTimer = setTimeout(() => fetchResults(q), DEBOUNCE_MS);
  }

  function onKeydown(e) {
    const items = resultsList.querySelectorAll('.hs-result');
    
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      updateActive(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, -1);
      updateActive(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && items[activeIndex]) {
        const url = items[activeIndex].dataset.url;
        if (url) window.location.href = url;
      }
    }
  }

  function updateActive(items) {
    items.forEach((el, i) => {
      el.classList.toggle('hs-active', i === activeIndex);
      if (i === activeIndex) el.scrollIntoView({ block: 'nearest' });
    });
  }

  // ─── API calls ────────────────────────────────────────
  async function fetchResults(query) {
    try {
      const resp = await fetch(`${API_BASE}/suggest?q=${encodeURIComponent(query)}&limit=${MAX_SUGGESTIONS}`);
      const data = await resp.json();
      renderSuggestions(data);
    } catch (err) {
      resultsList.innerHTML = '<div class="hs-empty hs-error">Chyba při vyhledávání</div>';
    }
  }

  function renderSuggestions(data) {
    const footer = overlay.querySelector('.hs-footer-time');
    footer.textContent = `${data.time_ms.toFixed(0)} ms`;

    if (!data.suggestions || data.suggestions.length === 0) {
      resultsList.innerHTML = `<div class="hs-empty">Nic nenalezeno pro "${escapeHtml(data.query)}"</div>`;
      activeIndex = -1;
      return;
    }

    activeIndex = -1;
    resultsList.innerHTML = data.suggestions.map((s, i) => `
      <a href="${escapeHtml(s.url)}" class="hs-result" data-url="${escapeHtml(s.url)}">
        <div class="hs-result-icon">
          ${getCategoryIcon(s.category)}
        </div>
        <div class="hs-result-body">
          <div class="hs-result-title">${highlightMatch(s.title, data.query)}</div>
          ${s.category ? `<div class="hs-result-cat">${escapeHtml(s.category)}</div>` : ''}
        </div>
        <svg class="hs-result-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </a>
    `).join('');

    // Click handlers
    resultsList.querySelectorAll('.hs-result').forEach(el => {
      el.addEventListener('click', (e) => {
        // Let default link behavior handle it
      });
    });
  }

  // ─── Helpers ──────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function highlightMatch(text, query) {
    const escaped = escapeHtml(text);
    const queryEscaped = escapeHtml(query);
    const regex = new RegExp(`(${queryEscaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
  }

  function getCategoryIcon(cat) {
    const icons = {
      'kuchyne': '🍳', 'kuchyně': '🍳',
      'obyvaci': '🛋️', 'obývací': '🛋️',
      'loznice': '🛏️', 'ložnice': '🛏️',
      'koupelny': '🚿',
      'predsin': '🚪', 'předsíň': '🚪',
      'jidelny': '🍽️', 'jídelny': '🍽️',
      'kolekce': '✨',
      'inspirace': '💡',
    };
    const lower = (cat || '').toLowerCase();
    for (const [key, icon] of Object.entries(icons)) {
      if (lower.includes(key)) return icon;
    }
    return '📄';
  }

  // ─── Global keyboard shortcut ─────────────────────────
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      isOpen ? close() : open();
    }
  });

  // ─── Inject search trigger button ─────────────────────
  function injectTrigger() {
    // Find existing search icon/button on the page
    const existing = document.querySelector(
      'a[href*="search"], .search-toggle, .search-icon, [data-search], .fa-search, .fa-magnifying-glass'
    );
    
    if (existing) {
      existing.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        open();
      });
    }

    // Also add floating search button
    const btn = document.createElement('button');
    btn.id = 'hanak-search-trigger';
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="20" height="20">
        <circle cx="11" cy="11" r="8"/>
        <path d="m21 21-4.35-4.35"/>
      </svg>
    `;
    btn.title = 'Vyhledávání (Ctrl+K)';
    btn.addEventListener('click', open);
    document.body.appendChild(btn);
  }

  // ─── Init ─────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectTrigger);
  } else {
    injectTrigger();
  }

})();
