import sqlite3
from database import get_connection
from notifications import notify
from appointments import (
    booking_lock, slot_problem, appt_info, when, ACTIVE
)

def request_reschedule(data):
    appointment_id = data.get("appointment_id")
    student_id = data.get("student_id")
    day, slot = data.get("day"), data.get("time_slot")
    reason = (data.get("reason") or "").strip()

    with booking_lock:
        con = get_connection()
        try:
            info = appt_info(con, appointment_id)
            if (info is None or info["student_id"] != student_id
                    or info["status"] not in ("Pending", "Accepted", "Rescheduled")):
                return {"success": False, "message": "Appointment not found"}

            if (info["day"], info["time_slot"]) == (day, slot):
                return {"success": False, "message": "Pick a different time"}

            problem = slot_problem(con, info["faculty_id"], day, slot,
                                   ignore_id=appointment_id)
            if problem:
                return {"success": False, "message": problem}

            con.execute("""
                INSERT INTO reschedule_requests
                (appointment_id, requested_by, new_day, new_time_slot, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (appointment_id, student_id, day, slot, reason))

            notify(con, info["faculty_id"], "reschedule_request",
                   f"{info['student']} asked to move "
                   f"{when(info['day'], info['time_slot'])} to {when(day, slot)}"
                   + (f" - {reason}" if reason else ""), appointment_id)

            con.commit()
            return {"success": True, "message": "Reschedule request sent to faculty"}

        except sqlite3.IntegrityError:
            con.rollback()
            return {"success": False, "message": "A reschedule request is already pending"}
        finally:
            con.close()

def respond_reschedule(data):
    action = data.get("action")
    if action not in ("Approved", "Declined"):
        return {"success": False, "message": "Action must be Approved or Declined"}

    with booking_lock:
        con = get_connection()
        try:
            req = con.execute("""
                SELECT r.*, a.faculty_id, a.student_id
                FROM reschedule_requests r
                JOIN appointments a ON a.appointment_id = r.appointment_id
                WHERE r.request_id=? AND r.status='Pending'
                  AND a.status IN """ + ACTIVE + """
            """, (data.get("request_id"),)).fetchone()

            if req is None or req["faculty_id"] != data.get("faculty_id"):
                return {"success": False, "message": "Request not found or already handled"}

            info = appt_info(con, req["appointment_id"])

            if action == "Approved":

                problem = slot_problem(con, req["faculty_id"], req["new_day"],
                                       req["new_time_slot"], ignore_id=req["appointment_id"])
                if problem:
                    return {"success": False, "message": problem + " - decline or move it directly"}

                con.execute("""
                    UPDATE appointments SET day=?, time_slot=?, status='Rescheduled'
                    WHERE appointment_id=?
                """, (req["new_day"], req["new_time_slot"], req["appointment_id"]))
                msg = (f"{info['faculty']} approved your reschedule: "
                       f"{when(info['day'], info['time_slot'])} -> "
                       f"{when(req['new_day'], req['new_time_slot'])}")
            else:
                msg = (f"{info['faculty']} declined your reschedule request; your meeting stays on "
                       f"{when(info['day'], info['time_slot'])}")

            con.execute("UPDATE reschedule_requests SET status=? WHERE request_id=?",
                        (action, req["request_id"]))
            notify(con, req["student_id"], "reschedule_" + action.lower(), msg,
                   req["appointment_id"])
            con.commit()
            return {"success": True, "message": "Reschedule " + action.lower()}

        except sqlite3.IntegrityError:
            con.rollback()
            return {"success": False, "message": "Appointment slot already booked"}
        finally:
            con.close()

def withdraw_reschedule(data):
    with booking_lock:
        con = get_connection()
        try:
            req = con.execute("""
                SELECT r.request_id, r.appointment_id, a.faculty_id
                FROM reschedule_requests r
                JOIN appointments a ON a.appointment_id = r.appointment_id
                WHERE r.request_id=? AND r.requested_by=? AND r.status='Pending'
            """, (data.get("request_id"), data.get("student_id"))).fetchone()
            if req is None:
                return {"success": False, "message": "Request not found"}

            info = appt_info(con, req["appointment_id"])
            con.execute("UPDATE reschedule_requests SET status='Withdrawn' WHERE request_id=?",
                        (req["request_id"],))
            notify(con, req["faculty_id"], "reschedule_withdrawn",
                   f"{info['student']} withdrew the reschedule request for "
                   f"{when(info['day'], info['time_slot'])}", req["appointment_id"])
            con.commit()
            return {"success": True, "message": "Request withdrawn"}
        finally:
            con.close()
