# promote_admin.py
import sqlite3, os, sys
DB = os.path.join(os.path.dirname(__file__), "survey.db")
email = sys.argv[1] if len(sys.argv)>1 else None
if not email: 
    print("Usage: python promote_admin.py you@example.com"); sys.exit(1)
con = sqlite3.connect(DB); cur = con.cursor()
cur.execute("UPDATE users SET is_admin=1 WHERE email=?", (email.lower(),))
if cur.rowcount==0:
    print("No user with that email."); sys.exit(2)
con.commit(); con.close()
print("OK: promoted to admin:", email)
