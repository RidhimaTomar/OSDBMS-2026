import sqlite3
import threading
from database import get_connection
from notifications import notify

booking_lock = threading.Lock()

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TIME_SLOTS = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
ACTIVE = "('Pending', 'Accepted', 'Rescheduled')"


def clean_venue(value):
    """Meeting place typed by the faculty (free text)."""
    return (value or "").strip()[:100]

def slot_problem(con, faculty_id, day, time_slot, ignore_id=None):
    if day not in DAYS or time_slot not in TIME_SLOTS:
        return "Invalid day or time slot"

    if con.execute("""
        SELECT 1 FROM timetable
        WHERE faculty_id=? AND day=? AND time_slot=?
    """, (faculty_id, day, time_slot)).fetchone():
        return "Faculty is teaching at this time"

    if con.execute("""
        SELECT 1 FROM appointments
        WHERE faculty_id=? AND day=? AND time_slot=?
        AND status IN """ + ACTIVE + """
        AND appointment_id IS NOT ?
    """, (faculty_id, day, time_slot, ignore_id)).fetchone():
        return "Appointment slot already booked"

    return None

def when(day, time_slot):
    return f"{day} {time_slot}"

def at(venue):
    return f" at {venue}" if venue else ""

def appt_info(con, appointment_id):
    return con.execute("""
        SELECT a.*, s.name AS student, f.name AS faculty, f.office AS faculty_office
        FROM appointments a
        JOIN users s ON a.student_id = s.user_id
        JOIN users f ON a.faculty_id = f.user_id
        WHERE a.appointment_id=?
    """, (appointment_id,)).fetchone()

def close_open_requests(con, appointment_id, new_status):
    con.execute("""
        UPDATE reschedule_requests SET status=?
        WHERE appointment_id=? AND status='Pending'
    """, (new_status, appointment_id))

def book_appointment(data):
    try:
        student_id = data["student_id"]
        faculty_id = data["faculty_id"]
        day = data["day"]
        time_slot = data["time_slot"]
    except KeyError:
        return {"success": False, "message": "Missing booking details"}

    topic = (data.get("topic") or "").strip()

    with booking_lock:
        con = get_connection()

        try:
            problem = slot_problem(con, faculty_id, day, time_slot)
            if problem:
                return {"success": False, "message": problem}

            # The venue is chosen later by the faculty when confirming the meeting.
            cur = con.execute("""
                INSERT INTO appointments
                (student_id, faculty_id, day, time_slot, topic)
                VALUES (?, ?, ?, ?, ?)
            """, (student_id, faculty_id, day, time_slot, topic))

            info = appt_info(con, cur.lastrowid)
            notify(con, faculty_id, "booking",
                   f"{info['student']} requested a meeting on {when(day, time_slot)}"
                   + (f" - {topic}" if topic else ""), cur.lastrowid)

            con.commit()
            return {"success": True, "message": "Request sent to faculty"}

        except sqlite3.IntegrityError:

            con.rollback()
            return {"success": False, "message": "Appointment slot or venue already booked"}

        except Exception as e:
            con.rollback()
            return {"success": False, "message": str(e)}

        finally:
            con.close()

def get_appointments(params=None):
    params = params or {}
    sql = """
        SELECT a.appointment_id, a.student_id, a.faculty_id,
               s.name AS student, f.name AS faculty,
               a.day, a.time_slot, a.topic, a.status,
               a.venue, f.office AS faculty_office,
               r.request_id AS req_id, r.new_day AS req_day,
               r.new_time_slot AS req_time, r.reason AS req_reason
        FROM appointments a
        JOIN users s ON a.student_id = s.user_id
        JOIN users f ON a.faculty_id = f.user_id
        LEFT JOIN reschedule_requests r
               ON r.appointment_id = a.appointment_id AND r.status = 'Pending'
        WHERE 1=1
    """
    args = []

    for key in ("student_id", "faculty_id"):
        if params.get(key):
            sql += " AND a." + key + "=?"
            args.append(params[key])

    sql += " ORDER BY a.appointment_id DESC"

    con = get_connection()
    rows = con.execute(sql, args).fetchall()
    con.close()

    return [dict(row) for row in rows]

def get_availability(params):
    faculty_id = params.get("faculty_id")

    con = get_connection()
    rows = con.execute("""
        SELECT day, time_slot FROM timetable WHERE faculty_id=?
        UNION
        SELECT day, time_slot FROM appointments
        WHERE faculty_id=? AND status IN """ + ACTIVE, (faculty_id, faculty_id)).fetchall()
    con.close()

    busy = {(r["day"], r["time_slot"]) for r in rows}

    return {
        "success": True,
        "slots": {d: [t for t in TIME_SLOTS if (d, t) not in busy] for d in DAYS}
    }

def respond_appointment(data):
    action = data.get("action")

    if action not in ("Accepted", "Rejected"):
        return {"success": False, "message": "Action must be Accepted or Rejected"}

    with booking_lock:
        con = get_connection()
        try:
            row = appt_info(con, data.get("appointment_id"))
            if (row is None or row["faculty_id"] != data.get("faculty_id")
                    or row["status"] != "Pending"):
                return {"success": False, "message": "Request not found or already handled"}

            # Confirming a meeting means telling the student where to meet (typed by the faculty).
            venue = ""
            if action == "Accepted":
                venue = clean_venue(data.get("venue"))
                if not venue:
                    return {"success": False, "message": "Enter where the meeting will take place"}

            con.execute("UPDATE appointments SET status=?, venue=? WHERE appointment_id=?",
                        (action, venue, row["appointment_id"]))

            info = appt_info(con, data.get("appointment_id"))
            notify(con, info["student_id"], action.lower(),
                   f"{info['faculty']} {action.lower()} your meeting on "
                   f"{when(info['day'], info['time_slot'])}{at(info['venue'])}", info["appointment_id"])
            con.commit()
        except sqlite3.IntegrityError:
            con.rollback()
            return {"success": False, "message": "Appointment slot already booked"}
        finally:
            con.close()

    return {"success": True, "message": "Booking " + action.lower()}

def reschedule_appointment(data):
    appointment_id = data.get("appointment_id")
    faculty_id = data.get("faculty_id")

    with booking_lock:
        con = get_connection()

        try:
            row = con.execute("""
                SELECT 1 FROM appointments
                WHERE appointment_id=? AND faculty_id=? AND status IN """ + ACTIVE,
                (appointment_id, faculty_id)).fetchone()

            if row is None:
                return {"success": False, "message": "Appointment not found"}

            before = appt_info(con, appointment_id)
            if (before["day"], before["time_slot"]) == (data.get("day"), data.get("time_slot")):
                return {"success": False, "message": "Booking is already at this time"}

            problem = slot_problem(con, faculty_id, data.get("day"),
                                   data.get("time_slot"), ignore_id=appointment_id)
            if problem:
                return {"success": False, "message": problem}

            # The meeting place stays the same unless the faculty types a new one.
            venue = clean_venue(data.get("venue")) or (before["venue"] or "")

            con.execute("""
                UPDATE appointments
                SET day=?, time_slot=?, venue=?, status='Rescheduled'
                WHERE appointment_id=?
            """, (data["day"], data["time_slot"], venue, appointment_id))

            close_open_requests(con, appointment_id, "Declined")

            after = appt_info(con, appointment_id)
            notify(con, before["student_id"], "rescheduled",
                   f"{before['faculty']} moved your meeting from "
                   f"{when(before['day'], before['time_slot'])} to "
                   f"{when(data['day'], data['time_slot'])}{at(after['venue'])}", appointment_id)

            con.commit()
            return {"success": True, "message": "Booking rescheduled"}

        except sqlite3.IntegrityError:
            con.rollback()
            return {"success": False, "message": "Appointment slot already booked"}

        finally:
            con.close()

def cancel_appointment(data):
    uid = data.get("user_id")
    con = get_connection()

    try:
        cur = con.execute("""
            UPDATE appointments
            SET status='Cancelled'
            WHERE appointment_id=? AND (student_id=? OR faculty_id=?)
            AND status IN """ + ACTIVE,
            (data.get("appointment_id"), uid, uid))

        if not cur.rowcount:
            return {"success": False, "message": "Appointment cannot be cancelled"}

        info = appt_info(con, data.get("appointment_id"))
        close_open_requests(con, info["appointment_id"], "Withdrawn")

        by_student = (uid == info["student_id"])
        notify(con, info["faculty_id"] if by_student else info["student_id"], "cancelled",
               f"{info['student'] if by_student else info['faculty']} cancelled the meeting on "
               f"{when(info['day'], info['time_slot'])}", info["appointment_id"])

        con.commit()
        return {"success": True, "message": "Appointment cancelled"}
    finally:
        con.close()

def set_meeting_venue(data):
    """Faculty changes where a confirmed meeting takes place (time stays the same)."""
    venue = clean_venue(data.get("venue"))
    if not venue:
        return {"success": False, "message": "Enter where the meeting will take place"}

    with booking_lock:
        con = get_connection()
        try:
            row = appt_info(con, data.get("appointment_id"))
            if (row is None or row["faculty_id"] != data.get("faculty_id")
                    or row["status"] not in ("Accepted", "Rescheduled")):
                return {"success": False, "message": "Appointment not found"}

            con.execute("UPDATE appointments SET venue=? WHERE appointment_id=?",
                        (venue, row["appointment_id"]))
            notify(con, row["student_id"], "venue",
                   f"{row['faculty']} set the meeting place for "
                   f"{when(row['day'], row['time_slot'])}{at(venue)}",
                   row["appointment_id"])
            con.commit()
            return {"success": True, "message": "Meeting place updated"}
        finally:
            con.close()