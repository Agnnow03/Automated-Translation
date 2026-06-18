"""
Build a Polish-English dictionary using Wiktionary (primary) with a Diki fallback.

This script queries the Wiktionary API for each Polish lemma from a frequency list
and attempts to extract English translations from the page wikitext. When Wiktionary
doesn't provide usable translations, it falls back to a lightweight Diki scrape
similar to the existing builder.

Usage: run from repository root, e.g.
    python scripts/build_polish_english_dictionary_wiktionary.py --count 5000

Note: be respectful of remote servers and rate limits.
"""
import argparse
import os
import re
import time
from typing import List

import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
DICT_FILE = os.path.join(ROOT, 'dictionary_PL_ENG_wiktionary.txt')
MEMORY_FILE = os.path.join(ROOT, 'translation_memory_PL_ENG_wiktionary.txt')
FREQ_URL = 'https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2016/pl/pl_50k.txt'
DIKI_SEARCH_URL = 'https://www.diki.pl/slownik-angielskiego?q={q}'

EN_TOKEN_RE = re.compile(r"[A-Za-z'-]{2,20}")


def download_top_polish_words(n=10000) -> List[str]:
    r = requests.get(FREQ_URL, timeout=30)
    r.encoding = 'utf-8'
    text = r.text
    words = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            words.append(parts[0])
        if len(words) >= n:
            break
    return words


def get_wikitext_from_en_wiktionary(word: str) -> str:
    API = 'https://en.wiktionary.org/w/api.php'
    params = {
        'action': 'query',
        'format': 'json',
        'formatversion': 2,
        'prop': 'revisions',
        'rvprop': 'content',
        'titles': word,
    }
    try:
        resp = requests.get(API, params=params, timeout=15)
        data = resp.json()
        pages = data.get('query', {}).get('pages', [])
        if not pages:
            return ''
        page = pages[0]
        if page.get('missing'):
            return ''
        revs = page.get('revisions') or []
        if not revs:
            return ''
        return revs[0].get('content', '') or ''
    except Exception:
        return ''


def clean_wikitext_markup(text: str) -> str:
    # Remove link markup [[a|b]] -> b, [[a]] -> a
    text = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", text)
    # Remove other templates like {{...}}
    text = re.sub(r"\{\{[^}]+\}\}", "", text)
    # Remove HTML comments and tags
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def extract_translations_from_wikitext(wikitext: str) -> List[str]:
    out = []
    if not wikitext:
        return out

    # Common translation template patterns: {{t|en|word}} or {{t+|en|word}}
    for m in re.finditer(r"\{\{t\+?\|en\|([^}\|]+)[^}]*\}\}", wikitext, flags=re.IGNORECASE):
        token = m.group(1).strip()
        token = clean_wikitext_markup(token)
        if token:
            out.append(token)

    # Some pages may use 'ang' as language code
    for m in re.finditer(r"\{\{t\+?\|ang\|([^}\|]+)[^}]*\}\}", wikitext, flags=re.IGNORECASE):
        token = m.group(1).strip()
        token = clean_wikitext_markup(token)
        if token:
            out.append(token)

    # Fallback: look for lines mentioning 'English' and collect candidate tokens
    for m in re.finditer(r"(?m)^[*#].*English[:\-]?\s*(.+)$", wikitext):
        part = m.group(1).strip()
        # split by commas or slashes
        for tok in re.split(r"[,/;]", part):
            tok = clean_wikitext_markup(tok)
            # keep english-looking tokens
            if EN_TOKEN_RE.fullmatch(tok):
                out.append(tok)

    # Final cleanup and uniqueness while preserving order
    seen = set()
    res = []
    for t in out:
        tl = t.lower()
        if tl in seen:
            continue
        seen.add(tl)
        res.append(t)
    return res


def fetch_diki_page(word: str) -> str:
    url = DIKI_SEARCH_URL.format(q=requests.utils.requote_uri(word))
    try:
        r = requests.get(url, timeout=15)
        r.encoding = 'utf-8'
        return r.text
    except Exception:
        return ''


def extract_candidate_translations_from_html(html: str) -> List[str]:
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    candidates = EN_TOKEN_RE.findall(text)
    junk = {'doctype', 'html', 'head', 'meta', 'charset', 'href', 'rel', 'class', 'svg', 'aria', 'xml'}
    seen = set()
    out = []
    for t in candidates:
        tl = t.lower()
        if tl in seen or tl in junk:
            continue
        if len(tl) < 2:
            continue
        if re.fullmatch(r"[0-9]+", tl):
            continue
        if re.search(r"[^A-Za-z\-']", tl):
            continue
        seen.add(tl)
        out.append(tl)
    return out


def build_dictionary(target_count: int = 10000, sleep_between=0.2):
    os.makedirs(os.path.dirname(DICT_FILE), exist_ok=True)
    pol_words = download_top_polish_words(n=target_count)
    with open(DICT_FILE, 'w', encoding='utf-8') as df, open(MEMORY_FILE, 'a', encoding='utf-8') as mf:
        for idx, pol in enumerate(pol_words, 1):
            print(f'[{idx}/{len(pol_words)}] processing', pol)
            wikitext = get_wikitext_from_en_wiktionary(pol)
            translations = extract_translations_from_wikitext(wikitext)
            # if wiktionary found translations, use them
            written = 0
            if translations:
                for tr in translations[:5]:
                    df.write(f"{pol}, {tr}\n")
                    written += 1
            else:
                # fallback to Diki scraping
                html = fetch_diki_page(pol)
                translations = extract_candidate_translations_from_html(html)
                for tr in translations[:5]:
                    df.write(f"{pol}, {tr}\n")
                    written += 1

            # try to extract example sentence pairs from HTML if present
            example_pairs = []
            example_pat = re.compile(r'<div class="exampleSentence">(.*?)<span class="exampleSentenceTranslation">(.*?)</span>', re.DOTALL | re.IGNORECASE)
            if 'html' in locals():
                for m in example_pat.finditer(html):
                    eng = re.sub('<[^>]+>', '', m.group(1)).strip()
                    pl = re.sub('<[^>]+>', '', m.group(2)).strip()
                    if pl and eng and pl.lower() != eng.lower():
                        example_pairs.append((pl, eng))
            for pl, eng in example_pairs[:2]:
                mf.write(f"{pl}, {eng}\n")

            if written == 0:
                df.write(f"{pol}, \n")
            time.sleep(sleep_between)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=10000, help='number of top Polish words to process')
    parser.add_argument('--sleep', type=float, default=0.2, help='sleep seconds between requests')
    args = parser.parse_args()
    build_dictionary(target_count=args.count, sleep_between=args.sleep)
