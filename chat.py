"""Student/faculty messaging."""
import re
from database import get_connection
from notifications import notify

MAX_MESSAGE = 2000


def _user(con, user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return con.execute("SELECT user_id, name, email, role FROM users WHERE user_id=?", (uid,)).fetchone()


def _valid_pair(a, b):
    return a and b and {a["role"], b["role"]} == {"Student", "Faculty"} and a["user_id"] != b["user_id"]


def get_chat_contacts(params):
    user_id = params.get("user_id")
    con = get_connection()
    try:
        me = _user(con, user_id)
        if not me or me["role"] not in ("Student", "Faculty"):
            return {"success": False, "message": "A student or faculty account is required"}

        if me["role"] == "Student":
            rows = con.execute("""
                SELECT u.user_id, u.name, u.email,
                    (SELECT message FROM chat_messages m
                     WHERE (m.sender_id=u.user_id AND m.recipient_id=?)
                        OR (m.sender_id=? AND m.recipient_id=u.user_id)
                     ORDER BY m.message_id DESC LIMIT 1) AS last_message,
                    (SELECT COUNT(*) FROM chat_messages m
                     WHERE m.sender_id=u.user_id AND m.recipient_id=? AND m.is_read=0) AS unread
                FROM users u WHERE u.role='Faculty' ORDER BY u.name
            """, (me["user_id"], me["user_id"], me["user_id"])).fetchall()
        else:
            rows = con.execute("""
                SELECT u.user_id, u.name, u.email,
                    (SELECT message FROM chat_messages m
                     WHERE (m.sender_id=u.user_id AND m.recipient_id=?)
                        OR (m.sender_id=? AND m.recipient_id=u.user_id)
                     ORDER BY m.message_id DESC LIMIT 1) AS last_message,
                    (SELECT COUNT(*) FROM chat_messages m
                     WHERE m.sender_id=u.user_id AND m.recipient_id=? AND m.is_read=0) AS unread
                FROM users u
                WHERE u.role='Student' AND (
                    EXISTS (SELECT 1 FROM appointments a WHERE a.student_id=u.user_id AND a.faculty_id=?)
                    OR EXISTS (SELECT 1 FROM chat_messages m WHERE
                        (m.sender_id=u.user_id AND m.recipient_id=?) OR
                        (m.sender_id=? AND m.recipient_id=u.user_id))
                ) ORDER BY u.name
            """, (me["user_id"], me["user_id"], me["user_id"], me["user_id"], me["user_id"], me["user_id"])).fetchall()
        return {"success": True, "contacts": [dict(r) for r in rows]}
    finally:
        con.close()


def get_chat_messages(params):
    user_id, other_id = params.get("user_id"), params.get("other_user_id")
    con = get_connection()
    try:
        me, other = _user(con, user_id), _user(con, other_id)
        if not _valid_pair(me, other):
            return {"success": False, "message": "Choose a valid student/faculty conversation"}
        con.execute("UPDATE chat_messages SET is_read=1 WHERE sender_id=? AND recipient_id=? AND is_read=0",
                    (other["user_id"], me["user_id"]))
        rows = con.execute("""
            SELECT message_id, sender_id, recipient_id, message, created_at
            FROM chat_messages
            WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)
            ORDER BY message_id ASC LIMIT 300
        """, (me["user_id"], other["user_id"], other["user_id"], me["user_id"])).fetchall()
        con.commit()
        return {"success": True, "messages": [dict(r) for r in rows], "contact": {"user_id": other["user_id"], "name": other["name"], "role": other["role"]}}
    finally:
        con.close()


def send_chat_message(data):
    user_id, other_id = data.get("user_id"), data.get("recipient_id")
    message = (data.get("message") or "").strip()
    if not message:
        return {"success": False, "message": "Write a message first"}
    if len(message) > MAX_MESSAGE:
        return {"success": False, "message": f"Messages must be {MAX_MESSAGE} characters or fewer"}

    con = get_connection()
    try:
        me, other = _user(con, user_id), _user(con, other_id)
        if not _valid_pair(me, other):
            return {"success": False, "message": "Only students and faculty can message each other"}
        cur = con.execute("INSERT INTO chat_messages(sender_id, recipient_id, message) VALUES(?,?,?)",
                          (me["user_id"], other["user_id"], message))
        notify(con, other["user_id"], "chat", f"New message from {me['name']}")
        con.commit()
        return {"success": True, "message": "Message sent", "message_id": cur.lastrowid}
    finally:
        con.close()