"""Sends email. Configure with environment variables (nothing is hard-coded).

Option A - SMTP (e.g. Gmail with an App Password):
    SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER=you@gmail.com
    SMTP_PASS=<app password>  MAIL_FROM="CampusSync <you@gmail.com>"
Option B - Resend HTTPS API (works where SMTP ports are blocked):
    RESEND_API_KEY=re_xxx  MAIL_FROM="CampusSync <noreply@your-domain>"

If neither is set, send_email() returns (False, reason) and the caller shows the link instead.
"""
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


def is_configured():
    return bool(os.environ.get("RESEND_API_KEY") or os.environ.get("SMTP_HOST"))


def send_email(to, subject, text, html=None):
    sender = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER") or ""
    if not is_configured() or not sender:
        return False, "Email is not configured on the server"

    try:
        if os.environ.get("RESEND_API_KEY"):
            body = {"from": sender, "to": [to], "subject": subject, "text": text}
            if html:
                body["html"] = html
            req = urllib.request.Request(
                "https://api.resend.com/emails", data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                         "Content-Type": "application/json", "User-Agent": "campussync/1.0"})
            with urllib.request.urlopen(req, timeout=15):
                pass
            return True, "sent"

        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT") or 587)
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            elif os.environ.get("SMTP_USER"):
                server.close()
                raise RuntimeError("mail server offers no TLS; refusing to send the password")
        with server:
            if os.environ.get("SMTP_USER"):
                server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
            server.send_message(msg)
        return True, "sent"
    except Exception as e:
        return False, "Could not send email: " + str(e)
