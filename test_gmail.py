import imaplib
import os

GMAIL_EMAIL = os.environ.get("GMAIL_EMAIL", "isroiljohnabdullayev@Gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "rvwdrkgucrpscuuv")

try:
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
    print("Muvaffaqiyatli ulana oldi!")
except Exception as e:
    print(f"Xato: {e}")
