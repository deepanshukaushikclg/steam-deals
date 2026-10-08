import json, os, smtplib, ssl, sys

def stop(m):
    print(m); sys.exit(0)

user, pw, to = ((os.environ.get(k) or "").strip() for k in ("MAIL_USER", "MAIL_PASS", "MAIL_TO"))
pw = pw.replace(" ", "")
if not (user and pw and to):
    stop("mail secrets not set, skipping")

free = json.load(open("data.json"))["free"]
try:
    seen = set(json.load(open("seen.json")))
except Exception:
    seen = set()

new = [g for g in free if g["url"] not in seen]
if not new:
    stop("no new free games")

from email.message import EmailMessage
body = "\n\n".join(f'{g["title"]}  (worth ₹{g["price_inr"]:,})\n{g["url"]}' for g in new)
msg = EmailMessage()
msg["Subject"] = f"{len(new)} Steam game(s) free now: " + ", ".join(g["title"] for g in new[:3])
msg["From"], msg["To"] = user, to
msg.set_content(body)

with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
    s.starttls(context=ssl.create_default_context())
    s.login(user, pw)
    s.send_message(msg)

json.dump(sorted(seen | {g["url"] for g in free}), open("seen.json", "w"))
print("mailed", len(new))
