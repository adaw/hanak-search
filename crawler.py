#!/usr/bin/env python3
"""Full recursive crawler for hanak-nabytek.cz — downloads EVERYTHING."""

import json
import os
import re
import sys
import time
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from collections import deque

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.hanak-nabytek.cz"
DOMAIN = "www.hanak-nabytek.cz"
SITE_DIR = Path.home() / "repos/hanak-search/site" / DOMAIN
PROJECT_DIR = Path.home() / "repos/hanak-search"
DELAY = 0.3
MAX_DEPTH = 20
TIMEOUT = 20

# Skip these URL patterns (AJAX junk)
SKIP_URL_PATTERNS = [
    '/oblibene/pridat/', '/oblibene/odebrat/',
    '/favoriten/add/', '/favoriten/entfernen/',
    '/favorites/add/', '/favorites/remove/',
    '/izbrannoe/dobavit/', '/izbrannoe/udalit/',
    '/favoris/ajouter/', '/favoris/supprimer/',
    '/oblubene/pridat/', '/oblubene/odobrat/',
    '?type=3216095',
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', stream=sys.stdout)
log = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'cs,en;q=0.5',
})

visited = set()
queued = set()

# Manifest tracking
manifest = {
    'html': [],
    'images': [],
    'pdfs': [],
    'other': [],
}
stats = {'html_new': 0, 'html_exist': 0, 'img_new': 0, 'img_exist': 0,
         'pdf_new': 0, 'pdf_exist': 0, 'errors': 0}

IMG_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp', '.avif'}
BINARY_SKIP = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv'}  # skip large video


def url_to_path(url: str) -> Path:
    parsed = urlparse(url)
    path = unquote(parsed.path).lstrip('/')
    if not path or path.endswith('/'):
        path = path + 'index.html'
    elif '.' not in os.path.basename(path):
        path = path + '.html'
    return SITE_DIR / path


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    # Strip tracking params but keep meaningful query
    query = parsed.query or ''
    if any(p in query for p in ['gad_', 'utm_', 'fbclid', 'gclid', 'no_cache']):
        query = ''
    if 'cHash' in query:
        # Remove cHash param but keep others
        parts = [p for p in query.split('&') if not p.startswith('cHash=')]
        query = '&'.join(parts)
    path = parsed.path
    url_clean = f"{parsed.scheme}://{parsed.netloc}{path}"
    if query:
        url_clean += f"?{query}"
    return url_clean


def is_internal(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc in ('', DOMAIN)


def should_skip(url: str) -> bool:
    return any(p in url for p in SKIP_URL_PATTERNS)


def extract_all_urls(html: str, base_url: str) -> tuple[set, set, set]:
    """Extract links, images, and asset URLs from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    images = set()
    assets = set()  # PDFs, other files

    # <a href>
    for tag in soup.find_all('a', href=True):
        href = tag['href'].strip()
        if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        full = urljoin(base_url, href)
        if not is_internal(full):
            continue
        ext = os.path.splitext(urlparse(full).path)[1].lower()
        if ext == '.pdf':
            assets.add(full)
        elif ext in IMG_EXT:
            images.add(full)
        else:
            links.add(full)

    # <img src> and srcset
    for tag in soup.find_all('img', src=True):
        src = urljoin(base_url, tag['src'].strip())
        if is_internal(src):
            images.add(src)
    for tag in soup.find_all(srcset=True):
        for part in tag['srcset'].split(','):
            s = part.strip().split()[0]
            if s:
                full = urljoin(base_url, s)
                if is_internal(full):
                    images.add(full)

    # CSS background images
    for tag in soup.find_all(style=True):
        for m in re.finditer(r'url\(["\']?([^"\')\s]+)["\']?\)', tag['style']):
            full = urljoin(base_url, m.group(1))
            if is_internal(full):
                images.add(full)

    # <source src/srcset> (video/picture)
    for tag in soup.find_all('source'):
        for attr in ('src', 'srcset'):
            val = tag.get(attr)
            if val:
                for part in val.split(','):
                    s = part.strip().split()[0]
                    if s:
                        full = urljoin(base_url, s)
                        if is_internal(full):
                            ext = os.path.splitext(urlparse(full).path)[1].lower()
                            if ext in IMG_EXT:
                                images.add(full)
                            elif ext == '.pdf':
                                assets.add(full)

    # <link href> for PDFs or other assets
    for tag in soup.find_all('link', href=True):
        full = urljoin(base_url, tag['href'].strip())
        if is_internal(full):
            ext = os.path.splitext(urlparse(full).path)[1].lower()
            if ext == '.pdf':
                assets.add(full)

    return links, images, assets


def download_file(url: str, category: str) -> bool:
    """Download a file. Returns True if new."""
    fpath = url_to_path(url)
    if fpath.exists():
        stats[f'{category}_exist'] += 1
        return False
    try:
        r = session.get(url, timeout=TIMEOUT, stream=True)
        if r.status_code != 200:
            return False
        # Limit: skip files > 100MB
        cl = r.headers.get('content-length')
        if cl and int(cl) > 100_000_000:
            log.warning(f"SKIP too large ({int(cl)//1_000_000}MB): {url}")
            return False
        fpath.parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        stats[f'{category}_new'] += 1
        return True
    except Exception as e:
        stats['errors'] += 1
        return False


def crawl():
    queue = deque()
    start = normalize_url(BASE_URL)
    queue.append((BASE_URL, 0))
    queued.add(start)

    page_count = 0
    img_queue = set()  # Collect images, download after HTML
    pdf_queue = set()

    while queue:
        url, depth = queue.popleft()
        norm = normalize_url(url)

        if norm in visited or should_skip(url):
            continue
        visited.add(norm)

        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext in BINARY_SKIP:
            continue
        if ext in IMG_EXT:
            img_queue.add(url)
            continue
        if ext == '.pdf':
            pdf_queue.add(url)
            continue

        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                stats['errors'] += 1
                time.sleep(DELAY)
                continue

            ct = r.headers.get('content-type', '')
            if 'text/html' not in ct and 'xhtml' not in ct:
                # Could be a PDF served without extension
                if 'pdf' in ct:
                    pdf_queue.add(url)
                time.sleep(DELAY)
                continue

            # Save HTML
            fpath = url_to_path(url)
            is_new = not fpath.exists()
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_bytes(r.content)
            if is_new:
                stats['html_new'] += 1
            else:
                stats['html_exist'] += 1
            manifest['html'].append(url)

            page_count += 1
            if page_count % 50 == 0 or (is_new and page_count % 10 == 0):
                log.info(f"[{page_count}] d={depth} q={len(queue)} imgs={len(img_queue)} pdfs={len(pdf_queue)} {url}")

            # Extract and queue
            if depth < MAX_DEPTH:
                links, images, assets = extract_all_urls(r.text, url)
                for link in links:
                    ln = normalize_url(link)
                    if ln not in queued and ln not in visited and not should_skip(link):
                        queue.append((link, depth + 1))
                        queued.add(ln)
                img_queue.update(images)
                pdf_queue.update(assets)

            time.sleep(DELAY)

        except Exception as e:
            log.error(f"ERR {url}: {e}")
            stats['errors'] += 1
            time.sleep(DELAY)

    # Phase 2: Download PDFs
    log.info(f"=== Phase 2: Downloading {len(pdf_queue)} PDFs ===")
    for i, url in enumerate(pdf_queue):
        is_new = download_file(url, 'pdf')
        manifest['pdfs'].append(url)
        if (i + 1) % 10 == 0:
            log.info(f"  PDF [{i+1}/{len(pdf_queue)}]")
        time.sleep(0.1)

    # Phase 3: Download images
    log.info(f"=== Phase 3: Downloading {len(img_queue)} images ===")
    for i, url in enumerate(img_queue):
        is_new = download_file(url, 'img')
        manifest['images'].append(url)
        if (i + 1) % 200 == 0:
            log.info(f"  IMG [{i+1}/{len(img_queue)}] new={stats['img_new']}")
        time.sleep(0.05)

    return page_count


def save_manifest():
    data = {
        'crawled_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'domain': DOMAIN,
        'stats': {
            'html_total': len(manifest['html']),
            'html_new': stats['html_new'],
            'images_total': len(manifest['images']),
            'images_new': stats['img_new'],
            'pdfs_total': len(manifest['pdfs']),
            'pdfs_new': stats['pdf_new'],
            'errors': stats['errors'],
        },
        'urls': {
            'html': sorted(set(manifest['html'])),
            'images': sorted(set(manifest['images'])),
            'pdfs': sorted(set(manifest['pdfs'])),
        }
    }
    out = PROJECT_DIR / 'crawl-manifest.json'
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log.info(f"Manifest saved: {out}")


def main():
    log.info("Starting FULL crawl (HTML + images + PDFs)")
    existing = sum(1 for _ in SITE_DIR.rglob('*.html')) if SITE_DIR.exists() else 0
    log.info(f"Existing HTML: {existing}")

    total = crawl()

    after_html = sum(1 for _ in SITE_DIR.rglob('*.html')) if SITE_DIR.exists() else 0
    log.info("=" * 60)
    log.info(f"CRAWL COMPLETE")
    log.info(f"HTML: {existing} → {after_html} (+{after_html - existing} new)")
    log.info(f"Stats: {stats}")

    save_manifest()


if __name__ == '__main__':
    main()
