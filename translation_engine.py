import hashlib
import os
import re
import string
import sqlite3
import threading
import difflib
import html
import ssl
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass
from typing import List, Optional
from types import SimpleNamespace
import language_tool_python

from constants.language_names import ENGLISH, POLISH, AVAILABLE_LANGUAGES
from segmentation.application.segmentation_service import SegmentationService

DICTIONARY_FILE = os.path.join(os.path.dirname(__file__), 'dictionary_PL_ENG.txt')
DIKI_SEARCH_URL_TEMPLATE = 'https://www.diki.pl/slownik-angielskiego?q={query}'
EXAMPLE_SENTENCE_PATTERN = re.compile(
    r'<div class="exampleSentence">(?P<english>.*?)<span class="exampleSentenceTranslation">(?P<polish>.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r'<[^>]+>')
POLISH_DIACRITICS = set('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ')
ENGLISH_SUFFIXES = (
    'ing', 'ed', 'er', 'or', 'ion', 'ment', 'ly', 'ness', 'ity', 'able',
    'ible', 'ous', 'ive', 'al', 'ate', 'ish', 'y', 'ic', 's', 'es', 'ist',
)
POLISH_SUFFIXES = (
    'anie', 'enie', 'ać', 'ić', 'owy', 'owa', 'owe', 'ność', 'stwo',
    'nia', 'nego', 'nych', 'owego', 'owaniu', 'owie', 'ami', 'ach', 'em',
    'ie', 'u', 'a', 'y', 'ów', 'om', 'ami', 'esz', 'isz', 'ę', 'ą',
)
ENGLISH_STOPWORDS = {
    'the', 'of', 'to', 'and', 'in', 'that', 'it', 'is', 'was', 'he', 'for',
    'on', 'are', 'as', 'with', 'his', 'they', 'i', 'at', 'be', 'this',
    'have', 'from', 'or', 'one', 'had', 'by', 'word', 'but', 'not', 'what',
    'all', 'were', 'we', 'when', 'your', 'can', 'said', 'there', 'use',
    'an', 'each', 'which', 'she', 'do', 'how', 'their', 'if', 'will',
    'up', 'other', 'about', 'out', 'many', 'then', 'them', 'these', 'so',
    'some', 'her', 'would', 'make', 'like', 'him', 'into', 'time', 'has',
    'look', 'two', 'more', 'write', 'go', 'see', 'number', 'no', 'way',
    'could', 'people', 'my', 'than', 'first', 'been', 'call', 'who', 'oil',
    'its', 'now', 'find', 'long', 'down', 'day', 'did', 'get', 'come',
    'made', 'may', 'part', 'hello', 'good', 'night', 'new', 'old', 'back',
    'many', 'some', 'other', 'your', 'their', 'more', 'also', 'than'
}


def normalize_exact(text: str) -> str:
    return ' '.join(text.strip().split())


def _score_polish_word(word: str) -> int:
    if any(ch in POLISH_DIACRITICS for ch in word):
        return 5
    w = word.lower()
    score = 0
    if any(w.endswith(s) for s in POLISH_SUFFIXES):
        score += 2
    if any(w.endswith(s) for s in ENGLISH_SUFFIXES):
        score -= 1
    if w in ENGLISH_STOPWORDS:
        score -= 3
    return score


def _score_english_word(word: str) -> int:
    if any(ch in POLISH_DIACRITICS for ch in word):
        return -10
    w = word.lower()
    score = 0
    if any(w.endswith(s) for s in ENGLISH_SUFFIXES):
        score += 2
    if any(w.endswith(s) for s in POLISH_SUFFIXES):
        score -= 1
    if w in ENGLISH_STOPWORDS:
        score += 2
    if re.match(r'^[0-9]+$', w):
        score += 1
    return score


def _detect_language(text: str) -> Optional[str]:
    tokens = re.findall(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+", text)
    if not tokens:
        return None

    polish_score = sum(_score_polish_word(token) for token in tokens)
    english_score = sum(_score_english_word(token) for token in tokens)
    if polish_score > english_score:
        return 'pl'
    if english_score > polish_score:
        return 'eng'
    return None


def _normalize_dictionary_pair(source: str, target: str):
    source_lang = _detect_language(source)
    target_lang = _detect_language(target)
    if source_lang == 'pl' and target_lang == 'eng':
        return source, target
    if source_lang == 'eng' and target_lang == 'pl':
        return target, source

    if source_lang == 'pl' or target_lang == 'eng':
        return source, target
    if target_lang == 'pl' or source_lang == 'eng':
        return target, source

    return source, target


def _strip_html(text: str) -> str:
    text = TAG_RE.sub('', text)
    return ' '.join(html.unescape(text).split())


def _clean_polish(text: str) -> str:
    cleaned = _strip_html(text).strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1].strip()
    return ' '.join(cleaned.split())


def fetch_diki_examples(query: str, max_examples: int = 30):
    encoded = urllib.parse.quote_plus(query)
    url = DIKI_SEARCH_URL_TEMPLATE.format(query=encoded)
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as response:
        html_text = response.read().decode('utf-8', errors='replace')

    examples = []
    for match in EXAMPLE_SENTENCE_PATTERN.finditer(html_text):
        english = _strip_html(match.group('english'))
        polish = _clean_polish(match.group('polish'))
        if english and polish and english.lower() != polish.lower():
            examples.append((polish, english))
        if len(examples) >= max_examples:
            break
    return examples


def normalize_fuzzy(text: str) -> str:
    normalized = normalize_exact(text).lower()
    cleaned = ''.join(ch for ch in normalized if ch not in string.punctuation)
    return ' '.join(cleaned.split())


def normalize_output(text: str) -> str:
    return normalize_exact(text)


def build_proposal(
    original: str,
    translation: str,
    score: float,
    note: str,
    matched_source: Optional[str] = None,
    matched_target: Optional[str] = None,
):
    proposal = {
        'original': original,
        'original_normalized': normalize_output(original),
        'translation': translation,
        'translation_normalized': normalize_output(translation),
        'score': float(score),
        'note': note,
    }
    if matched_source is not None:
        proposal['matched_sentence'] = matched_source
        proposal['matched_sentence_normalized'] = normalize_output(matched_source)
    if matched_target is not None:
        proposal['matched_translation'] = matched_target
        proposal['matched_translation_normalized'] = normalize_output(matched_target)
    return proposal


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_fuzzy(a), normalize_fuzzy(b)).ratio()


@dataclass
class TranslationMemoryEntry:
    polish: str
    english: str
    polish_exact: str
    english_exact: str
    polish_fuzzy: str
    english_fuzzy: str

    @classmethod
    def create(cls, polish: str, english: str):
        return cls(
            polish=polish.strip(),
            english=english.strip(),
            polish_exact=normalize_exact(polish),
            english_exact=normalize_exact(english),
            polish_fuzzy=normalize_fuzzy(polish),
            english_fuzzy=normalize_fuzzy(english),
        )


DICTIONARY_DB_FILE = os.path.join(os.path.dirname(__file__), 'dictionary_PL_ENG.db')

class Dictionary:
    def __init__(self, dictionary_file: Optional[str] = None, db_file: Optional[str] = None):
        self.dictionary_file = dictionary_file or DICTIONARY_FILE
        self.db_file = db_file or DICTIONARY_DB_FILE
        self.connection = sqlite3.connect(self.db_file, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._initialize_database()

    def _initialize_database(self):
        self.connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS dictionary (
                source_lang TEXT NOT NULL,
                source_word TEXT NOT NULL,
                target_word TEXT NOT NULL,
                PRIMARY KEY (source_lang, source_word)
            );
            '''
        )
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_dictionary_source ON dictionary(source_lang, source_word);'
        )
        self.connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            '''
        )
        self.connection.commit()
        self._load_dictionary_file()

    def _dictionary_file_checksum(self):
        sha = hashlib.sha256()
        with open(self.dictionary_file, 'rb') as file:
            for chunk in iter(lambda: file.read(8192), b''):
                sha.update(chunk)
        return sha.hexdigest()

    def _get_metadata(self, key: str) -> Optional[str]:
        row = self.connection.execute(
            'SELECT value FROM metadata WHERE key = ? LIMIT 1',
            (key,),
        ).fetchone()
        return row['value'] if row is not None else None

    def _set_metadata(self, key: str, value: str):
        self.connection.execute(
            'INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)',
            (key, value),
        )

    def _load_dictionary_file(self):
        if not os.path.exists(self.dictionary_file):
            return

        current_checksum = self._dictionary_file_checksum()
        stored_checksum = self._get_metadata('dictionary_checksum')

        with self.connection:
            existing = self.connection.execute('SELECT COUNT(1) FROM dictionary').fetchone()[0]
            if existing > 0 and stored_checksum == current_checksum:
                return
            if existing > 0 and stored_checksum != current_checksum:
                self.connection.execute('DELETE FROM dictionary')

            token_pattern = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+")
            rows = []
            with open(self.dictionary_file, 'r', encoding='utf-8') as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(',', 1)
                    if len(parts) < 2:
                        continue
                    source = parts[0].strip()
                    target = parts[1].strip()
                    polish_word, english_word = _normalize_dictionary_pair(source, target)
                    if not polish_word or not english_word:
                        continue
                    rows.append(('pl', polish_word.lower(), english_word.lower()))
                    rows.append(('eng', english_word.lower(), polish_word.lower()))
                    if len(rows) >= 10000:
                        self.connection.executemany(
                            'INSERT OR IGNORE INTO dictionary (source_lang, source_word, target_word) VALUES (?, ?, ?)',
                            rows,
                        )
                        rows = []
            if rows:
                self.connection.executemany(
                    'INSERT OR IGNORE INTO dictionary (source_lang, source_word, target_word) VALUES (?, ?, ?)',
                    rows,
                )
            self._set_metadata('dictionary_checksum', current_checksum)
            self.connection.commit()

            token_pattern = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+")
            rows = []
            with open(self.dictionary_file, 'r', encoding='utf-8') as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(',', 1)
                    if len(parts) < 2:
                        continue
                    source = parts[0].strip()
                    target = parts[1].strip()
                    polish_word, english_word = _normalize_dictionary_pair(source, target)
                    if not polish_word or not english_word:
                        continue
                    rows.append(('pl', polish_word.lower(), english_word.lower()))
                    rows.append(('eng', english_word.lower(), polish_word.lower()))
                    if len(rows) >= 10000:
                        self.connection.executemany(
                            'INSERT OR IGNORE INTO dictionary (source_lang, source_word, target_word) VALUES (?, ?, ?)',
                            rows,
                        )
                        rows = []
            if rows:
                self.connection.executemany(
                    'INSERT OR IGNORE INTO dictionary (source_lang, source_word, target_word) VALUES (?, ?, ?)',
                    rows,
                )
            self.connection.commit()

    def _tokenize(self, text: str):
        token_pattern = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+|[^\w\s]+|\s+")
        return token_pattern.findall(text)

    def _preserve_case(self, original: str, translated: str):
        if original.isupper():
            return translated.upper()
        if original.istitle():
            return translated.title()
        return translated

    def translate_word(self, word: str, source_lang: str, target_lang: str) -> str:
        lookup = word.lower()
        source_code = POLISH if source_lang == POLISH and target_lang == ENGLISH else ENGLISH
        if source_lang == POLISH and target_lang == ENGLISH:
            source_code = 'pl'
        elif source_lang == ENGLISH and target_lang == POLISH:
            source_code = 'eng'
        else:
            return word

        row = self.connection.execute(
            'SELECT target_word FROM dictionary WHERE source_lang = ? AND source_word = ? LIMIT 1',
            (source_code, lookup),
        ).fetchone()
        if row is None:
            return word
        return self._preserve_case(word, row['target_word'])

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        tokens = self._tokenize(text)
        translated = []
        for token in tokens:
            if token.isspace() or re.fullmatch(r"[^\w\s]+", token):
                translated.append(token)
            else:
                translated.append(self.translate_word(token, source_lang, target_lang))
        return ''.join(translated)


class TranslationMemory:
    def __init__(self, memory_file: Optional[str] = None):
        # Prefer JSON memory file if present; otherwise fall back to TXT
        default_txt = os.path.join(os.path.dirname(__file__), 'translation_memory_PL_ENG.txt')
        default_json = os.path.join(os.path.dirname(__file__), 'translation_memory_PL_ENG.json')
        if memory_file:
            self.memory_file = memory_file
        else:
            self.memory_file = default_json if os.path.exists(default_json) else default_txt

        self.connection = sqlite3.connect(':memory:', check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_schema(self.connection)
        self._load(self.connection)
        self.entries = self._load_entries()

    def _ensure_database_loaded(self):
        pass

    def _create_schema(self, conn):
        conn.execute(
            '''
            CREATE TABLE translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                polish TEXT NOT NULL,
                english TEXT NOT NULL,
                polish_exact TEXT NOT NULL,
                english_exact TEXT NOT NULL,
                polish_fuzzy TEXT NOT NULL,
                english_fuzzy TEXT NOT NULL
            );
            '''
        )
        conn.execute(
            'CREATE INDEX idx_polish_exact ON translation_memory(polish_exact);'
        )
        conn.execute(
            'CREATE INDEX idx_english_exact ON translation_memory(english_exact);'
        )
        conn.commit()

    def _load(self, conn):
        if not os.path.exists(self.memory_file):
            raise FileNotFoundError(f"Translation memory file not found: {self.memory_file}")

        rows = []
        seen_pairs = set()

        # JSON format support
        if self.memory_file.lower().endswith('.json'):
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = None
            translations = []
            if isinstance(data, dict) and isinstance(data.get('translations'), list):
                translations = data.get('translations')
            elif isinstance(data, list):
                translations = data

            normalized_translations = []
            for item in translations:
                if not isinstance(item, dict):
                    continue
                polish = item.get('polish')
                english = item.get('english')
                if not polish or not english:
                    continue
                polish_norm = normalize_exact(polish)
                english_norm = normalize_exact(english)
                if (polish_norm, english_norm) in seen_pairs:
                    continue
                seen_pairs.add((polish_norm, english_norm))
                normalized_translations.append({'polish': polish.strip(), 'english': english.strip()})
                rows.append((polish, english, polish_norm, english_norm, normalize_fuzzy(polish), normalize_fuzzy(english)))

            # If duplicates or messy formatting were present, rewrite normalized JSON
            if len(normalized_translations) != len(translations):
                out = {'translations': normalized_translations}
                with open(self.memory_file, 'w', encoding='utf-8') as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)

        else:
            normalized_lines = []
            with open(self.memory_file, 'r', encoding='utf-8') as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue

                    polish, english = self._parse_memory_line(line)
                    if polish is None or english is None:
                        continue

                    polish_norm = normalize_exact(polish)
                    english_norm = normalize_exact(english)
                    if (polish_norm, english_norm) in seen_pairs:
                        continue

                    seen_pairs.add((polish_norm, english_norm))
                    normalized_lines.append(f'{polish.strip()} @ {english.strip()}\n')
                    rows.append(
                        (
                            polish,
                            english,
                            polish_norm,
                            english_norm,
                            normalize_fuzzy(polish),
                            normalize_fuzzy(english),
                        )
                    )

            if normalized_lines:
                with open(self.memory_file, 'w', encoding='utf-8') as file:
                    file.writelines(normalized_lines)

        if rows:
            conn.executemany(
                '''
                INSERT INTO translation_memory
                (polish, english, polish_exact, english_exact, polish_fuzzy, english_fuzzy)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                rows,
            )
            conn.commit()

    def _row_to_entry(self, row):
        if row is None:
            return None
        return TranslationMemoryEntry(
            polish=row['polish'],
            english=row['english'],
            polish_exact=row['polish_exact'],
            english_exact=row['english_exact'],
            polish_fuzzy=row['polish_fuzzy'],
            english_fuzzy=row['english_fuzzy'],
        )

    def _parse_memory_line(self, line: str):
        if '@' in line:
            parts = line.split('@', 1)
        elif ', ' in line:
            parts = line.rsplit(', ', 1)
        elif ',' in line:
            parts = line.rsplit(',', 1)
        else:
            return None, None

        if len(parts) < 2:
            return None, None

        return parts[0].strip(), parts[1].strip()

    def _insert_entry(self, polish: str, english: str):
        self.connection.execute(
            '''
            INSERT OR IGNORE INTO translation_memory
            (polish, english, polish_exact, english_exact, polish_fuzzy, english_fuzzy)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                polish.strip(),
                english.strip(),
                normalize_exact(polish),
                normalize_exact(english),
                normalize_fuzzy(polish),
                normalize_fuzzy(english),
            ),
        )

    def _load_entries(self):
        with self._lock:
            rows = self.connection.execute('SELECT * FROM translation_memory').fetchall()
        return [self._row_to_entry(row) for row in rows]

    def clear_all_entries(self, remove_file: bool = True):
        """Remove all entries from the in-memory translation table and optionally truncate the backing file.

        Args:
            remove_file: If True, overwrite the translation memory file with no entries.
        Returns:
            Number of entries removed.
        """
        with self._lock:
            count = self.connection.execute('SELECT COUNT(1) FROM translation_memory').fetchone()[0]
            self.connection.execute('DELETE FROM translation_memory')
            self.connection.commit()
            self.entries = []

        if remove_file and os.path.exists(self.memory_file):
            # Truncate or reset the on-disk translation memory depending on format
            if self.memory_file.lower().endswith('.json'):
                with open(self.memory_file, 'w', encoding='utf-8') as f:
                    json.dump({'translations': []}, f, ensure_ascii=False, indent=2)
            else:
                with open(self.memory_file, 'w', encoding='utf-8') as f:
                    pass

        return count

    def append_pairs(self, pairs: List[tuple]):
        new_pairs = []
        existing_pairs = {(entry.polish_exact, entry.english_exact) for entry in self.entries}

        if self.memory_file.lower().endswith('.json'):
            # Load existing JSON
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = None
            translations = []
            if isinstance(data, dict) and isinstance(data.get('translations'), list):
                translations = data.get('translations')
            elif isinstance(data, list):
                translations = data
            else:
                translations = []

            for polish, english in pairs:
                polish_norm = normalize_exact(polish)
                english_norm = normalize_exact(english)
                if (polish_norm, english_norm) in existing_pairs:
                    continue
                translations.append({'polish': polish.strip(), 'english': english.strip()})
                self._insert_entry(polish, english)
                self.connection.commit()
                self.entries.append(TranslationMemoryEntry.create(polish, english))
                existing_pairs.add((polish_norm, english_norm))
                new_pairs.append((polish.strip(), english.strip()))

            # Write back JSON
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump({'translations': translations}, f, ensure_ascii=False, indent=2)

            return new_pairs

        # Fallback: plain text append
        with self._lock, open(self.memory_file, 'a', encoding='utf-8', newline='') as file:
            for polish, english in pairs:
                polish_norm = normalize_exact(polish)
                english_norm = normalize_exact(english)
                if (polish_norm, english_norm) in existing_pairs:
                    continue
                file.write(f'{polish.strip()} @ {english.strip()}\n')
                self._insert_entry(polish, english)
                self.connection.commit()
                self.entries.append(TranslationMemoryEntry.create(polish, english))
                existing_pairs.add((polish_norm, english_norm))
                new_pairs.append((polish.strip(), english.strip()))
        return new_pairs

    def find_exact(self, text: str, source_lang: str) -> Optional[TranslationMemoryEntry]:
        query = (
            'SELECT * FROM translation_memory WHERE polish_exact = ?'
            if source_lang == POLISH
            else 'SELECT * FROM translation_memory WHERE english_exact = ?'
        )
        with self._lock:
            row = self.connection.execute(query, (normalize_exact(text),)).fetchone()
        return self._row_to_entry(row)

    def find_best_source_match(
        self,
        text: str,
        source_lang: str,
        min_ratio: float = 0.45,
    ) -> Optional[TranslationMemoryEntry]:
        best_entry = None
        best_ratio = 0.0

        source_text = normalize_fuzzy(text)
        for entry in self.entries:
            candidate = entry.polish_fuzzy if source_lang == POLISH else entry.english_fuzzy
            ratio = difflib.SequenceMatcher(None, source_text, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry

        if best_entry is not None and best_ratio >= min_ratio:
            return best_entry
        return None

    def compute_context_bonus(
        self,
        previous_text: Optional[str],
        next_text: Optional[str],
        source_lang: str,
    ) -> float:
        bonus = 0.0
        if previous_text and self.find_exact(previous_text, source_lang):
            bonus += 0.1
        if next_text and self.find_exact(next_text, source_lang):
            bonus += 0.1
        return min(bonus, 0.2)

    def get_target_text(
        self,
        entry: TranslationMemoryEntry,
        source_lang: str,
        target_lang: str,
    ) -> str:
        if source_lang == target_lang:
            return entry.polish if target_lang == POLISH else entry.english
        if source_lang == POLISH and target_lang == ENGLISH:
            return entry.english
        if source_lang == ENGLISH and target_lang == POLISH:
            return entry.polish
        return entry.polish if target_lang == POLISH else entry.english


class TranslationService:
    def __init__(self):
        self.memory = TranslationMemory()
        self.dictionary = Dictionary()
        self.segmenter = SegmentationService()

    def fetch_and_store_diki_examples(self, query: str, max_examples: int = 30):
        pairs = fetch_diki_examples(query, max_examples)
        if not pairs:
            return []
        return self.memory.append_pairs(pairs)

    def translate_text(self, text: str, source_lang: str, target_lang: str):
        source_text = text.strip()
        if not source_text:
            return []

        if source_lang not in AVAILABLE_LANGUAGES:
            raise ValueError(f"Unknown source language: {source_lang}")
        if target_lang not in AVAILABLE_LANGUAGES:
            raise ValueError(f"Unknown target language: {target_lang}")

        segments = self.segmenter.segment(source_text, source_lang)
        if not segments:
            segments = [SimpleNamespace(text=source_text, previous_id=None, next_id=None)]

        proposals = []
        for idx, segment in enumerate(segments):
            sentence = segment.text.strip()
            if not sentence:
                continue

            previous_text = (
                segments[idx - 1].text.strip()
                if idx > 0 and segments[idx - 1].text
                else None
            )
            next_text = (
                segments[idx + 1].text.strip()
                if idx + 1 < len(segments) and segments[idx + 1].text
                else None
            )

            proposal = self._translate_sentence(
                sentence,
                source_lang,
                target_lang,
                previous_text,
                next_text,
            )
            proposals.append(proposal)

        return proposals

    def _translate_by_dictionary(self, sentence: str, source_lang: str, target_lang: str):
        translation = self.dictionary.translate_text(sentence, source_lang, target_lang)
        return translation

    def _improve_translation_with_dictionary(
        self,
        sentence: str,
        candidate_target: str,
        source_lang: str,
        target_lang: str,
    ):
        reference_translation = self._translate_by_dictionary(sentence, source_lang, target_lang)
        if not reference_translation or reference_translation == sentence:
            return candidate_target, similarity(candidate_target, reference_translation)

        word_pattern = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+")
        target_tokens = self.dictionary._tokenize(candidate_target)
        reference_tokens = self.dictionary._tokenize(reference_translation)

        target_word_indexes = [
            idx for idx, token in enumerate(target_tokens)
            if word_pattern.fullmatch(token)
        ]
        reference_word_tokens = [
            token for token in reference_tokens
            if word_pattern.fullmatch(token)
        ]

        if not target_word_indexes or not reference_word_tokens:
            return candidate_target, similarity(candidate_target, reference_translation)

        limit = min(len(target_word_indexes), len(reference_word_tokens))
        current_tokens = target_tokens[:]
        best_text = ''.join(current_tokens)
        best_score = similarity(best_text, reference_translation)

        improved = True
        while improved:
            improved = False
            for word_index in range(limit):
                token_index = target_word_indexes[word_index]
                replacement = reference_word_tokens[word_index]
                if current_tokens[token_index] == replacement:
                    continue

                trial_tokens = current_tokens[:]
                trial_tokens[token_index] = replacement
                trial_text = ''.join(trial_tokens)
                trial_score = similarity(trial_text, reference_translation)

                if trial_score > best_score + 1e-9:
                    current_tokens = trial_tokens
                    best_text = trial_text
                    best_score = trial_score
                    improved = True

        return best_text, best_score

    def _try_replace_low_similarity_words(
        self,
        sentence: str,
        candidate_target: str,
        source_lang: str,
        target_lang: str,
        base_similarity: float,
    ):
        dictionary_translation = self._translate_by_dictionary(sentence, source_lang, target_lang)
        replacement_similarity = similarity(dictionary_translation, candidate_target)
        if replacement_similarity > base_similarity + 0.1:
            return dictionary_translation, replacement_similarity
        return None, replacement_similarity

    def _replace_low_similarity_words_with_dictionary(
        self,
        sentence: str,
        candidate_source: str,
        candidate_target: str,
        source_lang: str,
        target_lang: str,
        max_replacements: Optional[int] = None,
    ):
        """Replace words in `candidate_target` using dictionary translations for
        source words that differ from the matched `candidate_source`.

        Returns the possibly-updated target text.
        """
        word_pat = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ']+")

        # Tokenize into word-lists (words only) for source and matched source
        src_tokens = [t for t in self.dictionary._tokenize(sentence) if word_pat.fullmatch(t)]
        matched_src_tokens = [t for t in self.dictionary._tokenize(candidate_source) if word_pat.fullmatch(t)]

        if not src_tokens or not matched_src_tokens:
            return candidate_target

        # Align source -> matched source to find which source words are low-similarity
        sm = difflib.SequenceMatcher(None, [s.lower() for s in src_tokens], [m.lower() for m in matched_src_tokens])
        low_sim_source_indexes = set()
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != 'equal':
                for i in range(i1, i2):
                    low_sim_source_indexes.add(i)

        if not low_sim_source_indexes:
            return candidate_target

        # Get dictionary word-by-word translation for the whole sentence
        dict_trans = self.dictionary.translate_text(sentence, source_lang, target_lang)
        dict_words = [t for t in self.dictionary._tokenize(dict_trans) if word_pat.fullmatch(t)]

        # Candidate target word tokens
        cand_target_tokens = self.dictionary._tokenize(candidate_target)
        cand_target_words = [t for t in cand_target_tokens if word_pat.fullmatch(t)]

        # If counts mismatch, we'll still try to map by index where possible
        updated = False
        # For each low-sim source word index, if dict has translation, try to replace corresponding
        # candidate target word (by same index if available)
        replacements_done = 0
        for src_idx in sorted(low_sim_source_indexes):
            if src_idx < len(dict_words):
                replacement = dict_words[src_idx]
                # find corresponding candidate target word index
                if src_idx < len(cand_target_words):
                    # replace the nth word occurrence in the full token list
                    target_word = cand_target_words[src_idx]
                    # locate the position of this nth word in the token stream
                    word_count = 0
                    for ti, tok in enumerate(cand_target_tokens):
                        if word_pat.fullmatch(tok):
                            if word_count == src_idx:
                                preserved = self.dictionary._preserve_case(tok, replacement)
                                cand_target_tokens[ti] = preserved
                                updated = True
                                replacements_done += 1
                                break
                            word_count += 1
            # If a maximum number of replacements is requested, stop after reaching it
            if max_replacements is not None and replacements_done >= max_replacements:
                break

        if not updated:
            return candidate_target

        return ''.join(cand_target_tokens)

    def _translate_sentence(
        self,
        sentence: str,
        source_lang: str,
        target_lang: str,
        previous_text: Optional[str],
        next_text: Optional[str],
    ):
        exact_entry = self.memory.find_exact(sentence, source_lang)
        if exact_entry is not None:
            translation = self.memory.get_target_text(exact_entry, source_lang, target_lang)
            return build_proposal(
                original=sentence,
                translation=translation,
                score=1.0,
                note='Exact translation found in the memory.',
                matched_source=sentence,
                matched_target=translation,
            )

        best_entry = self.memory.find_best_source_match(sentence, source_lang)
        dictionary_translation = self._translate_by_dictionary(sentence, source_lang, target_lang)

        if best_entry is not None:
            candidate_source = best_entry.polish if source_lang == POLISH else best_entry.english
            candidate_target = self.memory.get_target_text(best_entry, source_lang, target_lang)
            base_similarity = similarity(sentence, candidate_source)
            bonus = self.memory.compute_context_bonus(previous_text, next_text, source_lang)
            score = min(1.0, base_similarity + bonus)

            if base_similarity >= 0.80:
                # Before returning, try replacing up to 2 low-similarity words using dictionary
                replaced_target = self._replace_low_similarity_words_with_dictionary(
                    sentence, candidate_source, candidate_target, source_lang, target_lang, max_replacements=2
                )
                if replaced_target != candidate_target:
                    # Accept the replaced target only if it is sufficiently similar to the dictionary translation
                    if dictionary_translation:
                        sim_to_dict = similarity(replaced_target, dictionary_translation)
                        if sim_to_dict >= 0.90:
                            return build_proposal(
                                original=sentence,
                                translation=replaced_target,
                                score=score,
                                note=(
                                    'Suggested translation from the closest memory sentence with '
                                    'up to 2 low-similarity words replaced using the dictionary. '
                                    f'Similarity: {int(base_similarity * 100)}%, '
                                    f'context bonus: {int(bonus * 100)}%.'
                                ),
                                matched_source=candidate_source,
                                matched_target=candidate_target,
                            )
                        else:
                            # Fallback: use pure dictionary translation when replacement does not reach threshold
                            if dictionary_translation and dictionary_translation != sentence:
                                return build_proposal(
                                    original=sentence,
                                    translation=dictionary_translation,
                                    score=min(1.0, similarity(dictionary_translation, candidate_target)),
                                    note=(
                                        'Dictionary fallback: replacement did not sufficiently improve similarity; '
                                        'using dictionary-only translation.'
                                    ),
                                    matched_target=dictionary_translation,
                                )
                    else:
                        # No dictionary translation available — accept replaced target
                        return build_proposal(
                            original=sentence,
                            translation=replaced_target,
                            score=score,
                            note=(
                                'Suggested translation from the closest memory sentence with '
                                'up to 2 low-similarity words replaced using the dictionary. '
                                f'Similarity: {int(base_similarity * 100)}%, '
                                f'context bonus: {int(bonus * 100)}%.'
                            ),
                            matched_source=candidate_source,
                            matched_target=candidate_target,
                        )

                return build_proposal(
                    original=sentence,
                    translation=candidate_target,
                    score=score,
                    note=(
                        'Suggested translation from the closest memory sentence. '
                        f'Similarity: {int(base_similarity * 100)}%, '
                        f'context bonus: {int(bonus * 100)}%.'
                    ),
                    matched_source=candidate_source,
                    matched_target=candidate_target,
                )

            else:
                # For lower base similarity, try a conservative replacement of up to 2 words
                replaced_target = self._replace_low_similarity_words_with_dictionary(
                    sentence, candidate_source, candidate_target, source_lang, target_lang, max_replacements=2
                )
                if replaced_target != candidate_target:
                    if dictionary_translation:
                        sim_to_dict = similarity(replaced_target, dictionary_translation)
                        if sim_to_dict >= 0.90:
                            return build_proposal(
                                original=sentence,
                                translation=replaced_target,
                                score=min(1.0, sim_to_dict),
                                note=(
                                    'Conservatively improved low-similarity memory match by replacing up to 2 words using the dictionary.'
                                ),
                                matched_source=candidate_source,
                                matched_target=candidate_target,
                            )
                        else:
                            # fallback to dictionary-only translation when replaced target isn't good enough
                            if dictionary_translation and dictionary_translation != sentence:
                                return build_proposal(
                                    original=sentence,
                                    translation=dictionary_translation,
                                    score=min(1.0, similarity(dictionary_translation, candidate_target)),
                                    note=(
                                        'Dictionary fallback: conservative replacement did not reach similarity threshold; '
                                        'using dictionary-only translation.'
                                    ),
                                    matched_target=dictionary_translation,
                                )
                    else:
                        return build_proposal(
                            original=sentence,
                            translation=replaced_target,
                            score=min(1.0, similarity(replaced_target, candidate_target)),
                            note=(
                                'Conservatively improved low-similarity memory match by replacing up to 2 words using the dictionary.'
                            ),
                            matched_source=candidate_source,
                            matched_target=candidate_target,
                        )

            if dictionary_translation and dictionary_translation != sentence:
                improved_similarity = similarity(dictionary_translation, candidate_target)
                if improved_similarity > base_similarity + 0.08:
                    return build_proposal(
                        original=sentence,
                        translation=dictionary_translation,
                        score=min(1.0, improved_similarity),
                        note=(
                            'Low-similarity sentence improved by dictionary fallback. '
                            f'Dictionary text is more consistent than the memory match.'
                        ),
                        matched_source=candidate_source,
                        matched_target=candidate_target,
                    )

            if base_similarity >= 0.60:
                return build_proposal(
                    original=sentence,
                    translation=candidate_target,
                    score=score,
                    note=(
                        'Low-similarity memory match used because no better fallback was available. '
                        f'Similarity: {int(base_similarity * 100)}%.'
                    ),
                    matched_source=candidate_source,
                    matched_target=candidate_target,
                )

        if dictionary_translation and dictionary_translation != sentence:
            return build_proposal(
                original=sentence,
                translation=dictionary_translation,
                score=0.25,
                note='No suitable sentence match found; using word-by-word dictionary fallback.',
                matched_target=dictionary_translation,
            )

        exact_word_translation = self.dictionary.translate_text(sentence, source_lang, target_lang)
        return build_proposal(
            original=sentence,
            translation=exact_word_translation,
            score=0.1,
            note='No match found; using direct word-for-word dictionary translation.',
            matched_target=exact_word_translation,
        )


class SentenceCorrector:
    def __init__(self, memory: TranslationMemory):
        self.memory = memory
        self._lt_cache = {}

    def _cleanup_text(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r'\s+([?.!,;:])', r'\1', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        if cleaned and cleaned[-1] not in '.!?':
            cleaned = cleaned + '.'
        return cleaned

    def propose_corrections(self, text: str, source_lang: str):
        suggestions = []

        known_entry = self.memory.find_best_source_match(text, source_lang, min_ratio=0.75)
        if known_entry:
            known_source = known_entry.polish if source_lang == POLISH else known_entry.english
            if known_source != text and similarity(text, known_source) >= 0.75:
                suggestions.append({
                    'text': known_source,
                    'reason': 'Matched a known sentence from the translation memory.',
                })

        # LanguageTool suggestions for the language of the provided text
        try:
            lt_code = 'pl' if source_lang == POLISH else 'en-US'
            tool = self._lt_cache.get(lt_code)
            if tool is None:
                tool = language_tool_python.LanguageTool(lt_code)
                self._lt_cache[lt_code] = tool

            matches = tool.check(text)
            # Add up to 6 grammar/spelling suggestions
            for m in matches[:6]:
                if not m.replacements:
                    continue
                repl = m.replacements[0]
                start = m.offset
                end = m.offset + m.error_length
                suggested = text[:start] + repl + text[end:]
                rule_id = getattr(m, 'rule_id', None)
                reason = f'LanguageTool: {m.message}'
                if rule_id:
                    reason += f' (rule {rule_id})'
                suggestions.append({'text': suggested, 'reason': reason})
        except Exception:
            # if language tool not available or fails, ignore
            pass

        return suggestions
