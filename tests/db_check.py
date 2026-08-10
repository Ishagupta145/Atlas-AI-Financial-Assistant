import sqlite3

conn = sqlite3.connect('atlas.db')
cur = conn.cursor()
rows = list(cur.execute('SELECT telegram_user_id, memory_key, memory_value, created_at, updated_at FROM user_memory'))
for r in rows:
    print(r)
conn.close()
