# rename_user.py
import sqlite3
DB = r"C:\Users\hp\Desktop\survey_app\survey.db"

USER_ID = Adil          # <<< ID ـی ئەو هەژمارەی دەتەوێت ناوی بگۆڕیت
NEW_USERNAME = "ali_old"  # یوزەرنەیمی نوێ

con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("UPDATE users SET username=? WHERE id=?", (NEW_USERNAME, USER_ID))
print("rows updated:", cur.rowcount)
con.commit(); con.close()
