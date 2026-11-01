import sqlite3
from database import get_connection


# ---------- permission helpers ----------

def _editor_id(data):
    # The admin screens send admin_id; the faculty screen sends user_id.
    return data.get("admin_id") or data.get("user_id")


def _role(con, user_id):
    if not user_id:
        return None
    row = con.execute("SELECT role FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row["role"] if row else None


def _can_manage(con, editor_id, faculty_id):
    """Admin may change anyone's timetable; faculty may change only their own."""
    role = _role(con, editor_id)
    if role == "Admin":
        return True
    return role == "Faculty" and str(editor_id) == str(faculty_id)


def _missing(fields):
    """Subject, day and time are compulsory; room is optional (e.g. 'Meeting with HR')."""
    return not (fields["subject"] and fields["day"] and fields["time_slot"])


def _clean(data):
    return {
        "subject": str(data.get("subject") or "").strip(),
        "day": str(data.get("day") or "").strip(),
        "time_slot": str(data.get("time_slot") or "").strip(),
        "room": str(data.get("room") or "").strip(),
    }


# ---------- conflict checks ----------

def check_conflict(data):
    """Faculty / room clash check. If data has timetable_id, that row is ignored
    (so an entry being edited does not clash with itself)."""
    exclude = data.get("timetable_id") or 0
    con = get_connection()
    try:
        faculty = con.execute("""
            SELECT 1 FROM timetable
            WHERE faculty_id=? AND day=? AND time_slot=? AND timetable_id != ?
        """, (data["faculty_id"], data["day"], data["time_slot"], exclude)).fetchone()

        room = None
        if str(data.get("room") or "").strip():     # no room -> no room clash possible
            room = con.execute("""
                SELECT 1 FROM timetable
                WHERE room=? AND day=? AND time_slot=? AND timetable_id != ?
            """, (data["room"], data["day"], data["time_slot"], exclude)).fetchone()
    finally:
        con.close()

    if faculty:
        return {"conflict": True, "message": "Faculty is already busy"}

    if room:
        return {"conflict": True, "message": "Room is already occupied"}

    return {"conflict": False, "message": "No conflict"}


def _slot_has_booking(con, faculty_id, day, time_slot):
    return con.execute("""
        SELECT 1 FROM appointments
        WHERE faculty_id=? AND day=? AND time_slot=?
        AND status IN ('Pending', 'Accepted', 'Rescheduled')
    """, (faculty_id, day, time_slot)).fetchone()


# ---------- add / update / delete ----------

def add_timetable(data):
    if not data.get("faculty_id"):
        return {"success": False, "message": "Please enter a subject / description, day and time"}

    fields = _clean(data)
    if _missing(fields):
        return {"success": False, "message": "Please enter a subject / description, day and time"}

    con = get_connection()
    try:
        if not _can_manage(con, _editor_id(data), data["faculty_id"]):
            return {"success": False,
                    "message": "You can only change your own timetable"}
    finally:
        con.close()

    entry = {"faculty_id": data["faculty_id"], **fields}
    result = check_conflict(entry)
    if result["conflict"]:
        return {"success": False, "message": "Timetable conflict: " + result["message"]}

    con = get_connection()
    try:
        # A class cannot overwrite a student meeting that is already booked.
        if _slot_has_booking(con, entry["faculty_id"], entry["day"], entry["time_slot"]):
            return {"success": False,
                    "message": "A student appointment is already booked at that time"}

        con.execute("""
            INSERT INTO timetable (faculty_id, subject, day, time_slot, room)
            VALUES (?, ?, ?, ?, ?)
        """, (entry["faculty_id"], entry["subject"], entry["day"],
              entry["time_slot"], entry["room"]))
        con.commit()
        return {"success": True, "message": "Timetable entry added"}

    except sqlite3.IntegrityError as e:
        con.rollback()
        return {"success": False, "message": "Timetable conflict: " + str(e)}

    finally:
        con.close()


def update_timetable(data):
    """Edit an existing timetable entry (subject, day, time, room)."""
    con = get_connection()
    try:
        entry = con.execute("SELECT * FROM timetable WHERE timetable_id=?",
                            (data.get("timetable_id"),)).fetchone()
        if not entry:
            return {"success": False, "message": "Timetable entry not found"}

        if not _can_manage(con, _editor_id(data), entry["faculty_id"]):
            return {"success": False, "message": "You can only edit your own timetable"}

        fields = _clean(data)
        if _missing(fields):
            return {"success": False, "message": "Please enter a subject / description, day and time"}

        # Same checks as adding, but ignoring the entry being edited.
        result = check_conflict({
            "faculty_id": entry["faculty_id"], "timetable_id": entry["timetable_id"], **fields
        })
        if result["conflict"]:
            return {"success": False, "message": "Timetable conflict: " + result["message"]}

        moved = fields["day"] != entry["day"] or fields["time_slot"] != entry["time_slot"]
        if moved and _slot_has_booking(con, entry["faculty_id"], fields["day"], fields["time_slot"]):
            return {"success": False,
                    "message": "A student appointment is already booked at that time"}

        con.execute("""
            UPDATE timetable SET subject=?, day=?, time_slot=?, room=?
            WHERE timetable_id=?
        """, (fields["subject"], fields["day"], fields["time_slot"],
              fields["room"], entry["timetable_id"]))
        con.commit()
        return {"success": True, "message": "Timetable updated"}

    except sqlite3.IntegrityError as e:
        con.rollback()
        return {"success": False, "message": "Timetable conflict: " + str(e)}

    finally:
        con.close()


def delete_timetable(data):
    con = get_connection()
    try:
        entry = con.execute("SELECT faculty_id FROM timetable WHERE timetable_id=?",
                            (data.get("timetable_id"),)).fetchone()
        if not entry:
            return {"success": False, "message": "Timetable entry not found"}

        if not _can_manage(con, _editor_id(data), entry["faculty_id"]):
            return {"success": False, "message": "You can only change your own timetable"}

        con.execute("DELETE FROM timetable WHERE timetable_id=?", (data.get("timetable_id"),))
        con.commit()
        return {"success": True, "message": "Timetable entry removed"}
    finally:
        con.close()


def get_timetable(params=None):
    params = params or {}
    sql = """
        SELECT t.timetable_id, t.faculty_id, u.name AS faculty,
               t.subject, t.day, t.time_slot, t.room
        FROM timetable t
        JOIN users u ON t.faculty_id = u.user_id
    """
    args = ()
    if params.get("faculty_id"):
        sql += " WHERE t.faculty_id=?"
        args = (params["faculty_id"],)
    sql += " ORDER BY t.day, t.time_slot"

    con = get_connection()
    try:
        return [dict(row) for row in con.execute(sql, args).fetchall()]
    finally:
        con.close()
