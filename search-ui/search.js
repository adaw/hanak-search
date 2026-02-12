/**
 * Hanak Search — Clean oval bar + upward results
 * No fullscreen overlay — just a floating search widget
 */
(function() {
  'use strict';

  const API_BASE = '/api';
  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 120;
  const MAX_SUGGESTIONS = 8;
  const HANAK_ORIGIN = 'https://www.hanak-nabytek.cz';

  let container = null;
  let input = null;
  let resultsScroll = null;
  let resultsPanel = null;
  let trigger = null;
  let activeIndex = -1;
  let debounceTimer = null;
  let isOpen = false;

  // ─── Create DOM ───────────────────────────────────────
  function createContainer() {
    container = document.createElement('div');
    container.id = 'hanak-search-container';
    container.innerHTML = `
      <div class="hs-results-panel">
        <div class="hs-results-scroll"></div>
        <div class="hs-footer">
          <span class="hs-footer-hint">
            <kbd>↑↓</kbd> navigace &nbsp; <kbd>Enter</kbd> otevřít &nbsp; <kbd>Esc</kbd> zavřít
          </span>
          <span class="hs-footer-time"></span>
        </div>
      </div>
      <div class="hs-bar">
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
    `;
    document.body.appendChild(container);

    input = container.querySelector('.hs-input');
    resultsScroll = container.querySelector('.hs-results-scroll');
    resultsPanel = container.querySelector('.hs-results-panel');

    container.querySelector('.hs-close').addEventListener('click', close);
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);

    // Close on click outside
    document.addEventListener('click', (e) => {
      if (isOpen && !container.contains(e.target) && e.target !== trigger) {
        close();
      }
    });
  }

  // ─── Open / Close ─────────────────────────────────────
  function open() {
    if (!container) createContainer();
    isOpen = true;

    // Phase 1: expand trigger pill into bar shape
    trigger.classList.add('hs-expanded');

    // Phase 2: after expansion, show the real search container on top
    setTimeout(() => {
      container.classList.add('hs-active');
      trigger.classList.add('hs-hidden');
      trigger.classList.remove('hs-expanded');
      input.value = '';
      resultsScroll.innerHTML = '';
      resultsPanel.classList.remove('has-results');
      activeIndex = -1;
      input.focus();
    }, 380);
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    resultsPanel.classList.remove('has-results');
    container.classList.remove('hs-active');
    trigger.classList.remove('hs-hidden');
  }

  // ─── Input handling ───────────────────────────────────
  function onInput() {
    clearTimeout(debounceTimer);
    const q = input.value.trim();

    if (q.length < MIN_CHARS) {
      resultsScroll.innerHTML = '';
      resultsPanel.classList.remove('has-results');
      activeIndex = -1;
      return;
    }

    resultsScroll.innerHTML = '<div class="hs-loading"><div class="hs-spinner"></div></div>';
    resultsPanel.classList.add('has-results');
    debounceTimer = setTimeout(() => fetchResults(q), DEBOUNCE_MS);
  }

  function onKeydown(e) {
    const items = resultsScroll.querySelectorAll('.hs-result');

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
      resultsScroll.innerHTML = '<div class="hs-empty">Chyba při vyhledávání</div>';
      resultsPanel.classList.add('has-results');
    }
  }

  function renderSuggestions(data) {
    const footer = container.querySelector('.hs-footer-time');
    footer.textContent = `${data.time_ms.toFixed(0)} ms`;

    if (!data.suggestions || data.suggestions.length === 0) {
      resultsScroll.innerHTML = `<div class="hs-empty">Nic nenalezeno pro "${escapeHtml(data.query)}"</div>`;
      resultsPanel.classList.add('has-results');
      activeIndex = -1;
      return;
    }

    activeIndex = -1;
    resultsPanel.classList.add('has-results');
    resultsScroll.innerHTML = data.suggestions.map((s) => {
      const thumbHtml = s.image
        ? `<img src="${resolveImage(s.image)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<span class=hs-result-thumb-icon>📄</span>'">`
        : `<span class="hs-result-thumb-icon">${getCategoryIcon(s.category)}</span>`;

      const pct = s.score != null ? Math.min(100, Math.round(s.score * 100)) : null;
      const scoreHtml = pct != null ? `<span class="hs-result-score">${pct}%</span>` : '';

      return `
        <a href="${escapeHtml(s.url)}" class="hs-result" data-url="${escapeHtml(s.url)}">
          <div class="hs-result-thumb">${thumbHtml}</div>
          <div class="hs-result-body">
            <div class="hs-result-title">${highlightMatch(s.title, data.query)}</div>
            ${s.category ? `<div class="hs-result-cat">${escapeHtml(s.category)}</div>` : ''}
          </div>
          ${scoreHtml}
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

    trigger = document.createElement('button');
    trigger.id = 'hanak-search-trigger';
    trigger.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="18" height="18">
        <circle cx="11" cy="11" r="8"/>
        <path d="m21 21-4.35-4.35"/>
      </svg>
      <span>Hledat</span>
    `;
    trigger.title = 'Vyhledávání (Ctrl+K)';
    trigger.addEventListener('click', open);
    document.body.appendChild(trigger);
  }

  // ─── Init ─────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectTrigger);
  } else {
    injectTrigger();
  }
})();
