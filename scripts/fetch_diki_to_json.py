"""
Fetch Polish-English sentence pairs from Diki and save as JSON for testing.
"""
import os
import json
import ssl
import urllib.request
import urllib.parse
import re
import time
from typing import List, Dict

ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_FILE = os.path.join(ROOT, 'translation_memory_samples.json')
DIKI_SEARCH_URL = 'https://www.diki.pl/slownik-angielskiego?q={q}'
EXAMPLE_SENTENCE_PATTERN = re.compile(
    r'<div class="exampleSentence">(?P<english>.*?)<span class="exampleSentenceTranslation">(?P<polish>.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r'<[^>]+>')


def strip_html(text: str) -> str:
    text = TAG_RE.sub('', text)
    return ' '.join(text.split())


def clean_polish(text: str) -> str:
    cleaned = strip_html(text).strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1].strip()
    return ' '.join(cleaned.split())


def fetch_diki_examples(word: str, max_examples: int = 5) -> List[Dict[str, str]]:
    """Fetch example sentences for a word from Diki."""
    encoded = urllib.parse.quote_plus(word)
    url = DIKI_SEARCH_URL.format(q=encoded)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=20) as response:
            html_text = response.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'Error fetching {word}: {e}')
        return []

    examples = []
    for match in EXAMPLE_SENTENCE_PATTERN.finditer(html_text):
        english = strip_html(match.group('english'))
        polish = clean_polish(match.group('polish'))
        if english and polish and english.lower() != polish.lower():
            examples.append({'polish': polish, 'english': english})
        if len(examples) >= max_examples:
            break
    return examples


def main(target_count: int = 10):
    test_words = ['dzień', 'dom', 'książka', 'pies', 'kot', 'student', 'praca', 'samochód', 'plik', 'okno']
    all_examples = []

    for word in test_words:
        if len(all_examples) >= target_count:
            break
        print(f'Fetching examples for: {word}')
        examples = fetch_diki_examples(word, max_examples=2)
        all_examples.extend(examples)
        time.sleep(0.1)

    # Keep only target_count
    all_examples = all_examples[:target_count]

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_examples, f, ensure_ascii=False, indent=2)

    print(f'Saved {len(all_examples)} examples to {OUTPUT_FILE}')
    return all_examples


if __name__ == '__main__':
    main(target_count=10)
