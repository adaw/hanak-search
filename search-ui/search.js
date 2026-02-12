/**
 * Hanak Search — Expandable bottom bar with typeahead
 * Trigger: oval "Hledat" → expands left into search bar → results grow upward
 */
(function() {
  'use strict';

  const API_BASE = '/api';
  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 120;
  const MAX_SUGGESTIONS = 8;
  const HANAK_ORIGIN = 'https://www.hanak-nabytek.cz';

  let overlay = null;
  let bar = null;
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
      <div class="hs-bar">
        <div class="hs-results"></div>
        <div class="hs-footer">
          <span class="hs-footer-hint">
            <kbd>↑↓</kbd> navigace &nbsp; <kbd>Enter</kbd> otevřít &nbsp; <kbd>Esc</kbd> zavřít
          </span>
          <span class="hs-footer-time"></span>
        </div>
        <div class="hs-input-wrap">
          <svg class="hs-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <input type="text" class="hs-input" placeholder="Hledejte produkty, kolekce, realizace..." autocomplete="off" spellcheck="false">
          <button class="hs-close" title="Zavřít">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    bar = overlay.querySelector('.hs-bar');
    input = overlay.querySelector('.hs-input');
    resultsList = overlay.querySelector('.hs-results');

    // Events
    overlay.querySelector('.hs-backdrop').addEventListener('click', close);
    overlay.querySelector('.hs-close').addEventListener('click', close);
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);
  }

  // ─── Open / Close ─────────────────────────────────────
  function open() {
    if (!overlay) createOverlay();
    isOpen = true;
    overlay.classList.add('hs-active');
    input.value = '';
    resultsList.innerHTML = '';
    resultsList.classList.remove('has-results');
    activeIndex = -1;
    // Focus after animation
    setTimeout(() => input.focus(), 350);
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    resultsList.classList.remove('has-results');
    setTimeout(() => {
      overlay.classList.remove('hs-active');
      document.body.style.overflow = '';
    }, 100);
  }

  // ─── Input handling ───────────────────────────────────
  function onInput() {
    clearTimeout(debounceTimer);
    const q = input.value.trim();

    if (q.length < MIN_CHARS) {
      resultsList.innerHTML = '';
      resultsList.classList.remove('has-results');
      activeIndex = -1;
      return;
    }

    resultsList.innerHTML = '<div class="hs-loading"><div class="hs-spinner"></div></div>';
    resultsList.classList.add('has-results');
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
      if (activeIndex === -1) input.focus();
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
      resultsList.innerHTML = '<div class="hs-empty">Chyba při vyhledávání</div>';
      resultsList.classList.add('has-results');
    }
  }

  function renderSuggestions(data) {
    const footer = overlay.querySelector('.hs-footer-time');
    footer.textContent = `${data.time_ms.toFixed(0)} ms`;

    if (!data.suggestions || data.suggestions.length === 0) {
      resultsList.innerHTML = `<div class="hs-empty">Nic nenalezeno pro "${escapeHtml(data.query)}"</div>`;
      resultsList.classList.add('has-results');
      activeIndex = -1;
      return;
    }

    activeIndex = -1;
    resultsList.classList.add('has-results');
    resultsList.innerHTML = data.suggestions.map((s) => {
      const thumbHtml = s.image
        ? `<img src="${resolveImage(s.image)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<span class=hs-result-thumb-icon>📄</span>'">`
        : `<span class="hs-result-thumb-icon">${getCategoryIcon(s.category)}</span>`;

      return `
        <a href="${escapeHtml(s.url)}" class="hs-result" data-url="${escapeHtml(s.url)}">
          <div class="hs-result-thumb">${thumbHtml}</div>
          <div class="hs-result-body">
            <div class="hs-result-title">${highlightMatch(s.title, data.query)}</div>
            ${s.category ? `<div class="hs-result-cat">${escapeHtml(s.category)}</div>` : ''}
          </div>
          <svg class="hs-result-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </a>
      `;
    }).join('');
  }

  // ─── Helpers ──────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function highlightMatch(text, query) {
    const escaped = escapeHtml(text);
    const words = query.trim().split(/\s+/).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp(`(${words.join('|')})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
  }

  function resolveImage(url) {
    if (url.startsWith('http')) return url;
    return HANAK_ORIGIN + url;
  }

  function getCategoryIcon(cat) {
    const lower = (cat || '').toLowerCase();
    if (lower.includes('kuchyn')) return '🍳';
    if (lower.includes('realiz')) return '🏠';
    if (lower.includes('nabytek') || lower.includes('nábytek')) return '🪑';
    if (lower.includes('aktualn')) return '📰';
    if (lower.includes('developer')) return '🏗️';
    return '📄';
  }

  // ─── Global keyboard shortcut ─────────────────────────
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      isOpen ? close() : open();
    }
  });

  // ─── Inject trigger button ────────────────────────────
  function injectTrigger() {
    // Hijack existing search elements
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

    // Floating oval trigger
    const btn = document.createElement('button');
    btn.id = 'hanak-search-trigger';
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="18" height="18">
        <circle cx="11" cy="11" r="8"/>
        <path d="m21 21-4.35-4.35"/>
      </svg>
      <span>Hledat</span>
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
