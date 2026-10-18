import datetime
from database import get_connection
from appointments import DAYS, TIME_SLOTS, ACTIVE

def week_dates(today=None):
    today = today or datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    if today.weekday() >= 5:
        monday += datetime.timedelta(days=7)
    return [{"day": d,
             "date": (monday + datetime.timedelta(days=i)).isoformat(),
             "is_today": (monday + datetime.timedelta(days=i)) == today}
            for i, d in enumerate(DAYS)]

def get_calendar(params):
    try:
        uid = int(params.get("user_id"))
    except (TypeError, ValueError):
        return {"success": False, "message": "user_id required"}

    con = get_connection()
    try:
        me = con.execute("SELECT user_id, role FROM users WHERE user_id=?", (uid,)).fetchone()
        if me is None:
            return {"success": False, "message": "Unknown user"}
        role = me["role"]

        fid = params.get("faculty_id")
        if role == "Faculty":
            fid = uid
        elif fid:
            fid = int(fid)
        else:
            fid = None

        events = []

        sql = """SELECT t.day, t.time_slot, t.subject, t.room, u.name AS faculty
                 FROM timetable t JOIN users u ON t.faculty_id=u.user_id"""
        rows = con.execute(sql + (" WHERE t.faculty_id=?" if fid else ""),
                           (fid,) if fid else ()).fetchall() if (fid or role == "Admin") else []
        for r in rows:
            show = role != "Student"
            events.append({
                "day": r["day"], "time_slot": r["time_slot"], "kind": "class",
                "title": r["subject"] if show else "Class",
                "detail": ("Room " + r["room"] + (" - " + r["faculty"] if role == "Admin" else ""))
                          if show else "Faculty teaching"})

        where, args = "a.status IN " + ACTIVE, []
        if fid:
            where += " AND a.faculty_id=?"; args.append(fid)
        elif role == "Student":
            where += " AND a.student_id=?"; args.append(uid)

        rows = con.execute(f"""
            SELECT a.appointment_id, a.student_id, a.day, a.time_slot, a.topic, a.status,
                   s.name AS student, f.name AS faculty, a.venue AS venue
            FROM appointments a
            JOIN users s ON a.student_id=s.user_id
            JOIN users f ON a.faculty_id=f.user_id
            WHERE {where}""", args).fetchall()

        for r in rows:
            mine = (role == "Student" and r["student_id"] == uid)
            if role == "Student" and not mine:
                events.append({"day": r["day"], "time_slot": r["time_slot"], "kind": "busy",
                               "title": "Booked", "detail": "Taken by another student"})
                continue
            if role == "Faculty":
                title = r["student"]
            elif role == "Student":
                title = r["faculty"]
            else:
                title = f"{r['student']} / {r['faculty']}"
            events.append({"day": r["day"], "time_slot": r["time_slot"], "kind": "appointment",
                           "title": title,
                           "detail": (r["topic"] or "") + (" @ " + r["venue"] if r["venue"] else ""),
                           "venue": r["venue"], "status": r["status"],
                           "appointment_id": r["appointment_id"], "mine": True})

        pend = {r["appointment_id"]: dict(r) for r in con.execute("""
            SELECT appointment_id, new_day, new_time_slot FROM reschedule_requests
            WHERE status='Pending'""")}
        for e in events:
            p = pend.get(e.get("appointment_id"))
            if p:
                e["moving_to"] = f"{p['new_day']} {p['new_time_slot']}"

        return {"success": True, "role": role, "faculty_id": fid,
                "days": week_dates(), "slots": TIME_SLOTS, "events": events}
    finally:
        con.close()