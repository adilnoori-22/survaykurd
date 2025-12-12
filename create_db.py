import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

conn.commit()
conn.close()
print("📌 Database & Table created successfully!")

-- خشتەی profiles ئەگەر نییە، دروست بکە:
CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE,
  wallet_points INTEGER DEFAULT 0
);

-- ئەگەر ستوونی wallet_points لە profiles نییە، زیاد بکە:
ALTER TABLE profiles ADD COLUMN wallet_points INTEGER DEFAULT 0;

-- نرخی نال ببه‌ 0
UPDATE profiles SET wallet_points = COALESCE(wallet_points, 0);
