# reset_seed_admin.py — wipe all users and create one admin
import sqlite3, os, secrets, re
from datetime import datetime
from werkzeug.security import generate_password_hash

DB = r"C:\Users\hp\Desktop\survey_app\survey.db"  # لەوانەیە ڕێگای داتابەیس بگۆڕیت اگر جیاوازە
ADMIN_EMAIL = "adilask3@gmail.com"
ADMIN_USERNAME = re.sub(r"[^a-z0-9_]", "", ADMIN_EMAIL.split("@")[0].lower()) or "admin"
ADMIN_PASSWORD = "Admin@" + secrets.token_hex(4)  # پاسۆردێکی بەهێز دروست دەکات، لە کۆنساڵەدا دەچاپێت

def wipe_and_seed():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON;")
    cur = con.cursor()

    # سڕینەوەی هەموو داتای جەدۆڵە ژێر یوزەر
    tables = [
        "wallet_transactions",
        "profile_section_submissions",
        "profiles",
        "users"
    ]
    for t in tables:
        try:
            cur.execute(f"DELETE FROM {t}")
        except Exception:
            pass

    # دروستکردنی ئەدمین
    pw_hash = generate_password_hash(ADMIN_PASSWORD)
    cur.execute("""
        INSERT INTO users(username,password_hash,email,email_verified,
                          phone_code,phone,phone_verified,first_name,father_name,nickname,gender,
                          email_code,phone_code_token,code_expires,is_admin,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    """, (
        ADMIN_USERNAME, pw_hash, ADMIN_EMAIL, 1,
        "+964", "", 1, "Admin","-", "Admin", "M",
        None, None, None, 1
    ))
    uid = cur.lastrowid
    cur.execute("INSERT INTO profiles(user_id, wallet_points) VALUES (?,0)", (uid,))
    con.commit()
    con.close()

    print("\n[OK] هەموو یوزەرەکان سڕانەوە و ئەدمین دروست کرا ✅")
    print(f"  username: {ADMIN_USERNAME}")
    print(f"  email   : {ADMIN_EMAIL}")
    print(f"  password: {ADMIN_PASSWORD}\n")

if __name__ == "__main__":
    if not os.path.exists(DB):
        print(f"[ERR] DB not found: {DB}")
    else:
        wipe_and_seed()
