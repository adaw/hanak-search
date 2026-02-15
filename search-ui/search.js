/**
 * Hanak Search — Expanding pill + lightbox preview
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
  let isAnimating = false;
  let activeFilters = { text: true, image: true, document: false };

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
      <div class="hs-filters">
        <button class="hs-filter active" data-type="text">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M4 7h16M4 12h10M4 17h12"/></svg>
          Texty
        </button>
        <button class="hs-filter active" data-type="image">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
          Obrázky
        </button>
        <button class="hs-filter" data-type="document">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
          Dokumenty
        </button>
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

    // Filter toggle handlers
    container.querySelectorAll('.hs-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        const type = btn.dataset.type;
        activeFilters[type] = !activeFilters[type];
        btn.classList.toggle('active', activeFilters[type]);
        // Re-search with current query
        const q = input.value.trim();
        if (q.length >= MIN_CHARS) {
          clearTimeout(debounceTimer);
          fetchResults(q);
        }
      });
    });

    document.addEventListener('click', (e) => {
      if (isOpen && !container.contains(e.target) && e.target !== trigger) {
        close();
      }
    });
  }

  // ─── Open / Close with animations ────────────────────
  function open() {
    if (isAnimating || isOpen) return;
    if (!container) createContainer();
    isAnimating = true;

    // Phase 1: expand pill → bar shape
    trigger.classList.add('hs-expanded');

    // Phase 2: show real container seamlessly on top, hide trigger
    setTimeout(() => {
      container.classList.add('hs-active');
      trigger.classList.add('hs-gone');
      input.value = '';
      resultsScroll.innerHTML = '';
      resultsPanel.classList.remove('has-results');
      activeIndex = -1;
      input.focus();
      isOpen = true;
      isAnimating = false;
    }, 420);
  }

  function close() {
    if (isAnimating || !isOpen) return;
    isAnimating = true;
    isOpen = false;

    // Phase 1: hide container
    resultsPanel.classList.remove('has-results');
    container.classList.remove('hs-active');

    // Phase 2: show trigger in expanded state, then collapse
    trigger.classList.remove('hs-gone');
    trigger.classList.add('hs-expanded');

    // Small delay for container to fade, then collapse trigger
    setTimeout(() => {
      trigger.classList.remove('hs-expanded');
      trigger.classList.add('hs-collapsing');
    }, 80);

    // Phase 3: cleanup
    setTimeout(() => {
      trigger.classList.remove('hs-collapsing');
      isAnimating = false;
    }, 520);
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
        handleResultClick(items[activeIndex]);
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
      const typesParam = Object.entries(activeFilters).filter(([,v]) => v).map(([k]) => k).join(',');
      const resp = await fetch(`${API_BASE}/suggest?q=${encodeURIComponent(query)}&limit=${MAX_SUGGESTIONS}&types=${encodeURIComponent(typesParam)}`);
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
        <div class="hs-result" data-url="${escapeHtml(s.url)}" data-title="${escapeHtml(s.title)}" data-image="${s.image ? escapeHtml(resolveImage(s.image)) : ''}">
          <div class="hs-result-thumb">${thumbHtml}</div>
          <div class="hs-result-body">
            <div class="hs-result-title">${highlightMatch(s.title, data.query)}</div>
            ${s.category ? `<div class="hs-result-cat">${escapeHtml(s.category)}</div>` : ''}
          </div>
          ${scoreHtml}
          <svg class="hs-result-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </div>
      `;
    }).join('');

    // Attach click handlers
    resultsScroll.querySelectorAll('.hs-result').forEach(el => {
      el.addEventListener('click', () => handleResultClick(el));
    });
  }

  // ─── Lightbox ─────────────────────────────────────────
  function handleResultClick(el) {
    const image = el.dataset.image;
    const url = el.dataset.url;
    const title = el.dataset.title;

    if (image) {
      openLightbox(image, title, url);
    } else if (url) {
      window.location.href = url;
    }
  }

  function openLightbox(imageSrc, title, pageUrl) {
    const lb = document.createElement('div');
    lb.className = 'hs-lightbox';
    lb.innerHTML = `
      <div class="hs-lightbox-content">
        <img class="hs-lightbox-img" src="${imageSrc}" alt="${escapeHtml(title)}">
        <div class="hs-lightbox-info">
          <div class="hs-lightbox-title">${escapeHtml(title)}</div>
          <a class="hs-lightbox-link" href="${escapeHtml(pageUrl)}" target="_blank">Otevřít stránku →</a>
        </div>
      </div>
    `;
    document.body.appendChild(lb);

    // Fade in
    requestAnimationFrame(() => lb.classList.add('hs-lb-active'));

    // Close on backdrop click
    lb.addEventListener('click', (e) => {
      if (e.target === lb) {
        lb.classList.remove('hs-lb-active');
        setTimeout(() => lb.remove(), 250);
      }
    });

    // Close on Escape
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        lb.classList.remove('hs-lb-active');
        setTimeout(() => lb.remove(), 250);
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  }

  // ─── Helpers ──────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function highlightMatch(text, query) {
    const escaped = escapeHtml(text);
    const words = query.trim().split(/\s+/).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp(`(${words.join('|')})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
  }

  function resolveImage(url) {
    if (!url) return '';
    if (url.startsWith('http')) return url;
    // Strip leading ../ and ensure starts with /
    let clean = url.replace(/^(\.\.\/)+/, '/').replace(/^\/+/, '/');
    if (!clean.startsWith('/')) clean = '/' + clean;
    return HANAK_ORIGIN + clean;
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
      <svg viewBox="0 0 24 24" fill="none" stroke="#c5a36a" stroke-width="2.5" width="18" height="18">
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
