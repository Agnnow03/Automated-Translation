"""
Build a Polish-English dictionary by: 
- downloading a Polish frequency list (top N words),
- scraping Diki for candidate english translations and example sentences,
- falling back to simple heuristics when needed,
- writing results to ../dictionary_PL_ENG.txt and ../translation_memory_PL_ENG.txt (examples).

This is a best-effort, automated builder. Running it to collect ~10k words can take a long time
and may be subject to remote site rate limits. Use responsibly.
"""
import os
import re
import time
import ssl
import urllib.request
import urllib.parse
from typing import List

ROOT = os.path.dirname(os.path.dirname(__file__))
DICT_FILE = os.path.join(ROOT, 'dictionary_PL_ENG.txt')
MEMORY_FILE = os.path.join(ROOT, 'translation_memory_PL_ENG.txt')
FREQ_URL = 'https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2016/pl/pl_50k.txt'
DIKI_SEARCH_URL = 'https://www.diki.pl/slownik-angielskiego?q={q}'

# Simple token extraction and scoring to prefer english-looking tokens
EN_TOKEN_RE = re.compile(r"[A-Za-z'-]{2,20}")
POL_TOKEN_RE = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ'-]{2,20}")

def download_top_polish_words(n=10000) -> List[str]:
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(FREQ_URL, context=ctx, timeout=30) as r:
        text = r.read().decode('utf-8', errors='replace')
    words = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            words.append(parts[0])
        if len(words) >= n:
            break
    return words


def fetch_diki_page(word: str) -> str:
    url = DIKI_SEARCH_URL.format(q=urllib.parse.quote_plus(word))
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=20) as r:
            return r.read().decode('utf-8', errors='replace')
    except Exception:
        return ''


def extract_candidate_translations_from_html(html: str) -> List[str]:
    # Strip tags and decode entities
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # Find ASCII-looking tokens/phrases and filter obvious HTML junk
    candidates = EN_TOKEN_RE.findall(text)
    junk = {'doctype', 'html', 'head', 'meta', 'http-equiv', 'charset', 'href', 'rel', 'class', 'svg', 'aria', 'xml'}
    seen = set()
    out = []
    for t in candidates:
        tl = t.lower()
        if tl in seen or tl in junk:
            continue
        # skip single-letter tokens and tokens that are likely not English words
        if len(tl) < 2:
            continue
        # skip numeric tokens
        if re.fullmatch(r"[0-9]+", tl):
            continue
        # skip tokens with unexpected punctuation
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
            html = fetch_diki_page(pol)
            translations = extract_candidate_translations_from_html(html)
            # Write up to 5 distinct translations per polish word
            written = 0
            for tr in translations[:5]:
                df.write(f"{pol}, {tr}\n")
                written += 1
            # also try to fetch example sentence pairs using the example extractor if available
            # simple heuristic: look for sentences in the HTML and try to find english/polish pairs
            example_pairs = []
            # pattern used in repo: example sentence block
            example_pat = re.compile(r'<div class="exampleSentence">(.*?)<span class="exampleSentenceTranslation">(.*?)</span>', re.DOTALL|re.IGNORECASE)
            for m in example_pat.finditer(html):
                eng = re.sub('<[^>]+>', '', m.group(1)).strip()
                pl = re.sub('<[^>]+>', '', m.group(2)).strip()
                if pl and eng and pl.lower() != eng.lower():
                    example_pairs.append((pl, eng))
            for pl, eng in example_pairs[:2]:
                mf.write(f"{pl}, {eng}\n")
            # if no translations found, leave it for manual review
            if written == 0:
                df.write(f"{pol}, \n")
            time.sleep(sleep_between)


if __name__ == '__main__':
    # default run: build 10000-word dictionary
    build_dictionary(10000)
