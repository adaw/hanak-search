#!/usr/bin/env python3
"""
Inject search overlay into all HTML files in the scraped site.
Adds <link> and <script> tags before </body>.
"""

import os
import sys
from pathlib import Path

SITE_DIR = sys.argv[1] if len(sys.argv) > 1 else "site/www.hanak-nabytek.cz"
SEARCH_CSS = '<link rel="stylesheet" href="/search/search.css">'
SEARCH_JS = '<script src="/search/search.js" defer></script>'
INJECT_MARKER = '<!-- HANAK-SEARCH -->'


def inject_file(filepath: str) -> bool:
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return False

    if INJECT_MARKER in content:
        return False  # Already injected

    # Find </body> and inject before it
    if '</body>' in content:
        inject = f'\n{INJECT_MARKER}\n{SEARCH_CSS}\n{SEARCH_JS}\n'
        content = content.replace('</body>', inject + '</body>')
    elif '</html>' in content:
        inject = f'\n{INJECT_MARKER}\n{SEARCH_CSS}\n{SEARCH_JS}\n'
        content = content.replace('</html>', inject + '</html>')
    else:
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True


def main():
    html_files = list(Path(SITE_DIR).rglob("*.html"))
    print(f"Found {len(html_files)} HTML files in {SITE_DIR}")

    injected = 0
    for f in html_files:
        if inject_file(str(f)):
            injected += 1

    print(f"✅ Injected search into {injected} files")


if __name__ == "__main__":
    main()
