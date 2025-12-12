import sqlite3, os, sys
DB = os.path.join(os.path.dirname(__file__), "survey.db")
email = sys.argv[1].lower() if len(sys.argv)>1 else None
if not email:
    print("Usage: python force_verify.py you@example.com"); raise SystemExit
con = sqlite3.connect(DB); cur = con.cursor()
cur.execute("UPDATE users SET email_verified=1, email_verify_token=NULL WHERE email=?", (email,))
con.commit()
print("rows updated:", cur.rowcount)
con.close()
