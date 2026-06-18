"""
Rebuild the dictionary SQLite DB from the plaintext dictionary file.

This script chooses `dictionary_PL_ENG_wiktionary.txt` if present,
otherwise falls back to `dictionary_PL_ENG.txt` and recreates
`dictionary_PL_ENG.db` in the project directory.

Run:
    python scripts/rebuild_dictionary_db.py
"""
import os
import sys
import sqlite3

# Ensure repository root is on sys.path so imports work when running this script
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from translation_engine import Dictionary

wik_file = os.path.join(ROOT, 'dictionary_PL_ENG_wiktionary.txt')
txt_file = os.path.join(ROOT, 'dictionary_PL_ENG.txt')
alt_file = os.path.join(ROOT, 'pl_en_dictionary.txt')
db_file = os.path.join(ROOT, 'dictionary_PL_ENG.db')

if os.path.exists(wik_file):
    dict_file = wik_file
elif os.path.exists(txt_file):
    dict_file = txt_file
elif os.path.exists(alt_file):
    dict_file = alt_file
else:
    raise FileNotFoundError('No dictionary file found (dictionary_PL_ENG_wiktionary.txt or dictionary_PL_ENG.txt)')

if os.path.exists(db_file):
    # If DB is locked by another process, removing the file will fail.
    # Instead, connect and clear the dictionary table and remove stored checksum
    try:
        print('Resetting existing DB contents:', db_file)
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.execute('DELETE FROM dictionary')
        cur.execute("DELETE FROM metadata WHERE key = 'dictionary_checksum'")
        conn.commit()
        conn.close()
    except Exception:
        # Fall back to attempting to remove the file
        try:
            os.remove(db_file)
        except Exception as exc:
            raise

print('Rebuilding dictionary DB from', dict_file)
dictionary = Dictionary(dictionary_file=dict_file, db_file=db_file)

# Quick sanity: count entries
conn = sqlite3.connect(db_file)
cur = conn.cursor()
cur.execute("SELECT COUNT(1) FROM dictionary")
count = cur.fetchone()[0]
print('Dictionary entries (rows):', count)
conn.close()
