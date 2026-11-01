import sqlite3
import threading
from datetime import date as _date, timedelta
from database import get_connection
from notifications import notify

booking_lock = threading.Lock()

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TIME_SLOTS = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
ACTIVE = "('Pending', 'Accepted', 'Rescheduled')"
MAX_DAYS_AHEAD = 60


def clean_venue(value):
    """Meeting place typed by the faculty (free text)."""
    return (value or "").strip()[:100]


def parse_date(value):
    """Return (date, day_name, error). Only Mon-Fri, today or later, within 60 days."""
    try:
        d = _date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None, None, "Please choose a valid date"
    if d.weekday() > 4:
        return None, None, "Appointments are available Monday to Friday only"
    if d < _date.today():
        return None, None, "You cannot book a date in the past"
    if d > _date.today() + timedelta(days=MAX_DAYS_AHEAD):
        return None, None, f"You can book up to {MAX_DAYS_AHEAD} days ahead"
    return d, DAYS[d.weekday()], None


def _project_date(old_iso, day):
    """Date the booking lands on if only its weekday changes (same as the DB trigger)."""
    d = _date.fromisoformat(old_iso)
    return (d + timedelta(days=(DAYS.index(day) - d.weekday()) % 7)).isoformat()


def slot_problem(con, faculty_id, day, time_slot, ignore_id=None, appt_date=None):
    if day not in DAYS or time_slot not in TIME_SLOTS:
        return "Invalid day or time slot"

    # Only a weekday was given (e.g. a reschedule request): check the date it will land on.
    if appt_date is None and ignore_id is not None:
        r = con.execute("SELECT appt_date FROM appointments WHERE appointment_id=?",
                        (ignore_id,)).fetchone()
        if r and r["appt_date"]:
            appt_date = _project_date(r["appt_date"], day)

    if con.execute("""
        SELECT 1 FROM timetable
        WHERE faculty_id=? AND day=? AND time_slot=?
    """, (faculty_id, day, time_slot)).fetchone():
        return "Faculty is teaching at this time"

    # Same date, or an old undated (weekly) booking on that weekday.
    if con.execute("""
        SELECT 1 FROM appointments
        WHERE faculty_id=? AND day=? AND time_slot=?
        AND status IN """ + ACTIVE + """
        AND appointment_id IS NOT ?
        AND (appt_date=? OR appt_date IS NULL OR appt_date='')
    """, (faculty_id, day, time_slot, ignore_id, appt_date)).fetchone():
        return "Appointment slot already booked"

    return None


def when(day, time_slot, appt_date=None):
    if appt_date:
        d = _date.fromisoformat(appt_date)
        return f"{day} {d.day} {d.strftime('%b')} {time_slot}"
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
        time_slot = data["time_slot"]
    except KeyError:
        return {"success": False, "message": "Missing booking details"}

    d, day, err = parse_date(data.get("date"))
    if err:
        return {"success": False, "message": err}
    appt_date = d.isoformat()

    topic = (data.get("topic") or "").strip()

    with booking_lock:
        con = get_connection()

        try:
            problem = slot_problem(con, faculty_id, day, time_slot, appt_date=appt_date)
            if problem:
                return {"success": False, "message": problem}

            cur = con.execute("""
                INSERT INTO appointments
                (student_id, faculty_id, day, time_slot, appt_date, topic)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (student_id, faculty_id, day, time_slot, appt_date, topic))

            info = appt_info(con, cur.lastrowid)
            notify(con, faculty_id, "booking",
                   f"{info['student']} requested a meeting on {when(day, time_slot, appt_date)}"
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
               a.day, a.time_slot, a.appt_date, a.topic, a.status,
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
    """Free slots per weekday. With ?date=YYYY-MM-DD that date's weekday is exact.
    With ?upcoming=1 also returns a list of free (date, slot) options for the next 3 weeks."""
    faculty_id = params.get("faculty_id")

    con = get_connection()
    try:
        tt = {(r["day"], r["time_slot"]) for r in con.execute(
            "SELECT day, time_slot FROM timetable WHERE faculty_id=?", (faculty_id,))}
        appts = con.execute("""SELECT day, time_slot, appt_date FROM appointments
                               WHERE faculty_id=? AND status IN """ + ACTIVE,
                            (faculty_id,)).fetchall()
    finally:
        con.close()

    base = tt | {(r["day"], r["time_slot"]) for r in appts if not r["appt_date"]}
    slots = {d: [t for t in TIME_SLOTS if (d, t) not in base] for d in DAYS}
    booked_on = {}
    for r in appts:
        if r["appt_date"]:
            booked_on.setdefault(r["appt_date"], set()).add(r["time_slot"])

    result = {"success": True, "slots": slots}

    if params.get("date"):
        d, day, err = parse_date(params["date"])
        if err:
            return {"success": False, "message": err, "slots": {x: [] for x in DAYS}}
        taken = booked_on.get(d.isoformat(), set())
        slots[day] = [t for t in slots[day] if t not in taken]

    if params.get("upcoming"):
        options, today = [], _date.today()
        for i in range(21):
            d = today + timedelta(days=i)
            if d.weekday() > 4:
                continue
            day, taken = DAYS[d.weekday()], booked_on.get(d.isoformat(), set())
            for t in TIME_SLOTS:
                if (day, t) not in base and t not in taken:
                    options.append({"date": d.isoformat(), "day": day, "time_slot": t})
        result["options"] = options

    return result


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
                   f"{when(info['day'], info['time_slot'], info['appt_date'])}{at(info['venue'])}",
                   info["appointment_id"])
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

            if data.get("date"):
                d, new_day, err = parse_date(data["date"])
                if err:
                    return {"success": False, "message": err}
                new_date = d.isoformat()
            elif before["appt_date"]:
                return {"success": False, "message": "Choose a new date and time"}
            else:
                new_day, new_date = data.get("day"), ""

            new_slot = data.get("time_slot")
            if (before["day"], before["time_slot"], before["appt_date"] or "") == (new_day, new_slot, new_date):
                return {"success": False, "message": "Booking is already at this time"}

            problem = slot_problem(con, faculty_id, new_day, new_slot,
                                   ignore_id=appointment_id, appt_date=new_date or None)
            if problem:
                return {"success": False, "message": problem}

            # The meeting place stays the same unless the faculty types a new one.
            venue = clean_venue(data.get("venue")) or (before["venue"] or "")

            con.execute("""
                UPDATE appointments
                SET day=?, time_slot=?, appt_date=?, venue=?, status='Rescheduled'
                WHERE appointment_id=?
            """, (new_day, new_slot, new_date, venue, appointment_id))

            close_open_requests(con, appointment_id, "Declined")

            after = appt_info(con, appointment_id)
            notify(con, before["student_id"], "rescheduled",
                   f"{before['faculty']} moved your meeting from "
                   f"{when(before['day'], before['time_slot'], before['appt_date'])} to "
                   f"{when(new_day, new_slot, new_date)}{at(after['venue'])}", appointment_id)

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
               f"{when(info['day'], info['time_slot'], info['appt_date'])}", info["appointment_id"])

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
                   f"{when(row['day'], row['time_slot'], row['appt_date'])}{at(venue)}",
                   row["appointment_id"])
            con.commit()
            return {"success": True, "message": "Meeting place updated"}
        finally:
            con.close()
