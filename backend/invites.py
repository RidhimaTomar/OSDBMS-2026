import datetime
import hashlib
import html
import os
import re
import secrets
import sqlite3

from database import get_connection
from security import hash_password
from users import is_admin
from mailer import send_email, is_configured

INVITE_HOURS = 48
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FMT = "%Y-%m-%d %H:%M:%S"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _hash(token):
    # Only the hash is stored, so a database leak does not leak usable links.
    return hashlib.sha256((token or "").encode()).hexdigest()


def create_invitation(data):
    admin_id = data.get("admin_id")
    if not is_admin(admin_id):
        return {"success": False, "message": "Only admin can invite faculty"}

    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    if not EMAIL_RE.match(email):
        return {"success": False, "message": "Enter a valid email address"}

    base = (os.environ.get("APP_BASE_URL") or data.get("_base_url") or "").rstrip("/")

    con = get_connection()
    try:
        if con.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
            return {"success": False, "message": "A user with this email already exists"}

        # A new invite replaces any older live one for the same address.
        con.execute("UPDATE invitations SET status='Revoked' WHERE email=? AND status='Pending'", (email,))

        token = secrets.token_urlsafe(32)
        expires = _now() + datetime.timedelta(hours=INVITE_HOURS)
        con.execute("""
            INSERT INTO invitations(email, name, token_hash, invited_by, expires_at)
            VALUES (?,?,?,?,?)
        """, (email, name, _hash(token), admin_id, expires.strftime(FMT)))
        con.commit()
    finally:
        con.close()

    link = f"{base}/?invite={token}"
    who = name or "there"
    text = (f"Hello {who},\n\nYou have been invited to join CampusSync as a faculty member.\n"
            f"Create your account here (valid for {INVITE_HOURS} hours, one use):\n{link}\n\n"
            "If you were not expecting this, you can ignore this email.")
    page = (f"<p>Hello {html.escape(who)},</p><p>You have been invited to join <b>CampusSync</b> "
            f"as a faculty member.</p><p><a href=\"{html.escape(link)}\">Create your account</a> "
            f"(valid for {INVITE_HOURS} hours, one use).</p>"
            "<p>If you were not expecting this, you can ignore this email.</p>")
    sent, detail = send_email(email, "You're invited to CampusSync", text, page)

    if sent:
        return {"success": True, "email_sent": True, "message": "Invitation emailed to " + email}

    # Fallback so the flow still works without a mail server: admin shares the link by hand.
    print("INVITE LINK for", email, "->", link, "|", detail)
    return {"success": True, "email_sent": False, "invite_link": link,
            "message": "Invitation created but email was not sent (" + detail + "). Share the link manually."}


def list_invitations(params):
    if not is_admin(params.get("admin_id")):
        return {"success": False, "message": "Only admin can view invitations"}
    con = get_connection()
    try:
        now = _now().strftime(FMT)
        rows = con.execute("""
            SELECT invitation_id, email, name, status, created_at, expires_at,
                   CASE WHEN status='Pending' AND expires_at < ? THEN 'Expired' ELSE status END AS state
            FROM invitations WHERE status != 'Revoked'
            ORDER BY invitation_id DESC LIMIT 50
        """, (now,)).fetchall()
        return {"success": True, "invitations": [dict(r) for r in rows],
                "email_configured": is_configured()}
    finally:
        con.close()


def revoke_invitation(data):
    if not is_admin(data.get("admin_id")):
        return {"success": False, "message": "Only admin can revoke invitations"}
    con = get_connection()
    try:
        cur = con.execute("UPDATE invitations SET status='Revoked' WHERE invitation_id=? AND status='Pending'",
                          (data.get("invitation_id"),))
        con.commit()
        if not cur.rowcount:
            return {"success": False, "message": "Invitation not found or already used"}
        return {"success": True, "message": "Invitation revoked"}
    finally:
        con.close()


def _live_invite(con, token):
    return con.execute("""
        SELECT invitation_id, email, name FROM invitations
        WHERE token_hash=? AND status='Pending' AND expires_at >= ?
    """, (_hash(token), _now().strftime(FMT))).fetchone()


def check_invitation(params):
    con = get_connection()
    try:
        inv = _live_invite(con, params.get("token"))
        if inv is None:
            return {"success": False, "message": "This invitation link is invalid or has expired"}
        return {"success": True, "email": inv["email"], "name": inv["name"]}
    finally:
        con.close()


def accept_invitation(data):
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    if not name:
        return {"success": False, "message": "Please enter your name"}
    if len(password) < 8:
        return {"success": False, "message": "Password must be at least 8 characters"}

    con = get_connection()
    try:
        inv = _live_invite(con, data.get("token"))
        if inv is None:
            return {"success": False, "message": "This invitation link is invalid or has expired"}

        # Claim the invite first; if two people use the link at once only one wins.
        claimed = con.execute(
            "UPDATE invitations SET status='Accepted' WHERE invitation_id=? AND status='Pending'",
            (inv["invitation_id"],))
        if not claimed.rowcount:
            con.rollback()
            return {"success": False, "message": "This invitation was already used"}

        con.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'Faculty')",
                    (name, inv["email"], hash_password(password)))
        con.commit()
        return {"success": True, "message": "Account created. You can now log in."}
    except sqlite3.IntegrityError:
        con.rollback()
        return {"success": False, "message": "An account with this email already exists"}
    finally:
        con.close()
