import sqlite3
from database import get_connection
from users import is_admin


def check_conflict(data):
    con = get_connection()

    faculty = con.execute("""
        SELECT * FROM timetable
        WHERE faculty_id=? AND day=? AND time_slot=?
    """, (
        data["faculty_id"],
        data["day"],
        data["time_slot"]
    )).fetchone()

    room = con.execute("""
        SELECT * FROM timetable
        WHERE room=? AND day=? AND time_slot=?
    """, (
        data["room"],
        data["day"],
        data["time_slot"]
    )).fetchone()

    con.close()

    if faculty:
        return {"conflict": True, "message": "Faculty is already busy"}

    if room:
        return {"conflict": True, "message": "Room is already occupied"}

    return {"conflict": False, "message": "No conflict"}


def add_timetable(data):
    if not is_admin(data.get("admin_id")):
        return {"success": False, "message": "Only admin can change the timetable"}

    for field in ("faculty_id", "subject", "day", "time_slot", "room"):
        if not data.get(field):
            return {"success": False, "message": "All fields are required"}

    result = check_conflict(data)
    if result["conflict"]:
        return {"success": False, "message": "Timetable conflict: " + result["message"]}

    con = get_connection()

    try:
        # A class cannot overwrite a student meeting that is already booked.
        booked = con.execute("""
            SELECT 1 FROM appointments
            WHERE faculty_id=? AND day=? AND time_slot=?
            AND status IN ('Pending', 'Accepted', 'Rescheduled')
        """, (data["faculty_id"], data["day"], data["time_slot"])).fetchone()

        if booked:
            return {
                "success": False,
                "message": "A student appointment is already booked at that time"
            }

        con.execute("""
            INSERT INTO timetable
            (faculty_id, subject, day, time_slot, room)
            VALUES (?, ?, ?, ?, ?)
        """, (
            data["faculty_id"],
            data["subject"],
            data["day"],
            data["time_slot"],
            data["room"]
        ))
        con.commit()
        return {"success": True, "message": "Timetable entry added"}

    except sqlite3.IntegrityError as e:
        con.rollback()
        return {"success": False, "message": "Timetable conflict: " + str(e)}

    finally:
        con.close()


def delete_timetable(data):
    if not is_admin(data.get("admin_id")):
        return {"success": False, "message": "Only admin can change the timetable"}

    con = get_connection()
    con.execute("DELETE FROM timetable WHERE timetable_id=?", (data.get("timetable_id"),))
    con.commit()
    con.close()

    return {"success": True, "message": "Timetable entry removed"}


def get_timetable():
    con = get_connection()
    rows = con.execute("""
        SELECT t.timetable_id, t.faculty_id, u.name AS faculty,
               t.subject, t.day, t.time_slot, t.room
        FROM timetable t
        JOIN users u ON t.faculty_id = u.user_id
        ORDER BY t.day, t.time_slot
    """).fetchall()
    con.close()

    return [dict(row) for row in rows]
