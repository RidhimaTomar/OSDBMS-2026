import datetime
from database import get_connection

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def notify(con, user_id, kind, message, appointment_id=None, dedupe_key=None):
    con.execute("""
        INSERT OR IGNORE INTO notifications
        (user_id, kind, message, appointment_id, dedupe_key)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, kind, message, appointment_id, dedupe_key))

def generate_reminders(con, today=None):
    today = today or datetime.date.today()
    day = DAY_NAMES[today.weekday()]
    rows = con.execute("""
        SELECT a.appointment_id, a.student_id, a.faculty_id, a.time_slot, a.topic,
               s.name AS student, f.name AS faculty
        FROM appointments a
        JOIN users s ON a.student_id = s.user_id
        JOIN users f ON a.faculty_id = f.user_id
        WHERE a.day=? AND a.status IN ('Accepted', 'Rescheduled')
    """, (day,)).fetchall()

    for r in rows:
        key = f"reminder:{r['appointment_id']}:{today.isoformat()}"
        notify(con, r["student_id"], "reminder",
               f"Reminder: meeting with {r['faculty']} today at {r['time_slot']}",
               r["appointment_id"], f"{key}:s")
        notify(con, r["faculty_id"], "reminder",
               f"Reminder: meeting with {r['student']} today at {r['time_slot']}",
               r["appointment_id"], f"{key}:f")
    con.commit()

def get_notifications(params):
    user_id = params.get("user_id")
    if not user_id:
        return {"success": False, "message": "user_id required"}

    con = get_connection()
    try:
        generate_reminders(con)
        rows = con.execute("""
            SELECT notification_id, kind, message, appointment_id, is_read, created_at
            FROM notifications WHERE user_id=?
            ORDER BY notification_id DESC LIMIT 100
        """, (user_id,)).fetchall()
        unread = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user_id,)).fetchone()[0]
        return {"success": True, "unread": unread,
                "notifications": [dict(r) for r in rows]}
    finally:
        con.close()

def mark_read(data):
    user_id = data.get("user_id")
    nid = data.get("notification_id")
    con = get_connection()
    try:
        if nid:
            con.execute("UPDATE notifications SET is_read=1 WHERE notification_id=? AND user_id=?",
                        (nid, user_id))
        else:
            con.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
        con.commit()
        return {"success": True, "message": "Marked as read"}
    finally:
        con.close()