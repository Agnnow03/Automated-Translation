"""
Append entries from `pl_en_dictionary.txt` into `dictionary_PL_ENG.db`.

This script reads each line, splits on the first comma, and inserts
both pl->en and en->pl rows using INSERT OR IGNORE to avoid duplicates.

Run:
    python scripts/append_pl_en_dictionary.py
"""
import os
import sys
import sqlite3

# repo root
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

dict_txt = os.path.join(ROOT, 'pl_en_dictionary.txt')
db_file = os.path.join(ROOT, 'dictionary_PL_ENG.db')

if not os.path.exists(dict_txt):
    raise FileNotFoundError(f'Input dictionary file not found: {dict_txt}')
if not os.path.exists(db_file):
    raise FileNotFoundError(f'Dictionary DB not found: {db_file}')

conn = sqlite3.connect(db_file)
cur = conn.cursor()

to_insert = []
with open(dict_txt, 'r', encoding='utf-8') as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if ',' not in line:
            continue
        parts = line.split(',', 1)
        polish = parts[0].strip()
        english = parts[1].strip()
        if not polish or not english:
            continue
        # store lowercase for lookup consistency
        to_insert.append(('pl', polish.lower(), english.lower()))
        to_insert.append(('eng', english.lower(), polish.lower()))

# batch insert using INSERT OR IGNORE
cur.executemany(
    'INSERT OR IGNORE INTO dictionary (source_lang, source_word, target_word) VALUES (?, ?, ?)',
    to_insert,
)
conn.commit()

# report count
cur.execute('SELECT COUNT(1) FROM dictionary')
count = cur.fetchone()[0]
print('Dictionary rows after append:', count)
conn.close()
