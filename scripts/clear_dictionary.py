import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(__file__))
DICT_TXT = os.path.join(BASE, 'dictionary_PL_ENG.txt')
DICT_DB = os.path.join(BASE, 'dictionary_PL_ENG.db')

# Truncate dictionary file
with open(DICT_TXT, 'w', encoding='utf-8') as f:
    pass
print('Truncated', DICT_TXT)

# If DB exists, clear its tables; otherwise remove file if present
if os.path.exists(DICT_DB):
    try:
        conn = sqlite3.connect(DICT_DB)
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS dictionary")
        cur.execute("DROP TABLE IF EXISTS metadata")
        conn.commit()
        conn.close()
        print('Cleared tables in', DICT_DB)
    except Exception as e:
        print('Error clearing DB tables:', e)
else:
    print('No DB file found at', DICT_DB)
