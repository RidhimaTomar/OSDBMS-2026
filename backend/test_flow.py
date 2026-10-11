import os, tempfile
os.environ["CAMPUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from database import init_db, get_connection
init_db()
from appointments import book_appointment, respond_appointment, reschedule_appointment, cancel_appointment, get_appointments
from reschedule import request_reschedule, respond_reschedule, withdraw_reschedule
from notifications import get_notifications, mark_read
from calendar_view import get_calendar

S, F, F2 = 3, 2, 4
def kinds(u): return [n["kind"] for n in get_notifications({"user_id": u})["notifications"]][::-1]
ok = lambda r: r["success"]

assert ok(book_appointment({"student_id": S, "faculty_id": F, "day": "Mon", "time_slot": "14:00", "topic": "t"}))
assert kinds(F) == ["booking"]
assert ok(respond_appointment({"appointment_id": 1, "faculty_id": F, "action": "Accepted"}))
assert kinds(S) == ["accepted"]

assert not ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Mon", "time_slot": "14:00"}))
assert not ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Mon", "time_slot": "09:00"}))
assert not ok(request_reschedule({"appointment_id": 1, "student_id": 99, "day": "Tue", "time_slot": "14:00"}))
assert ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Tue", "time_slot": "14:00", "reason": "lab"}))
assert not ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Wed", "time_slot": "14:00"}))
assert get_appointments({"faculty_id": F})[0]["req_day"] == "Tue"
cal = get_calendar({"user_id": S})
assert cal["events"][0]["moving_to"] == "Tue 14:00"

assert ok(respond_reschedule({"request_id": 1, "faculty_id": F, "action": "Declined"}))
assert get_appointments({"student_id": S})[0]["day"] == "Mon"

assert ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Tue", "time_slot": "14:00"}))
assert ok(withdraw_reschedule({"request_id": 2, "student_id": S}))
assert ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Wed", "time_slot": "15:00"}))

con = get_connection(); con.execute("INSERT INTO users(name,email,password,role) VALUES('B','b@x','x','Student')"); con.commit(); con.close()
assert ok(book_appointment({"student_id": 5, "faculty_id": F, "day": "Wed", "time_slot": "15:00", "topic": "x"}))
r = respond_reschedule({"request_id": 3, "faculty_id": F, "action": "Approved"}); assert not ok(r), r
assert ok(cancel_appointment({"appointment_id": 2, "user_id": 5}))
assert ok(respond_reschedule({"request_id": 3, "faculty_id": F, "action": "Approved"}))
a = get_appointments({"student_id": S})[0]
assert (a["day"], a["time_slot"], a["status"]) == ("Wed", "15:00", "Rescheduled")
assert not ok(respond_reschedule({"request_id": 3, "faculty_id": F, "action": "Approved"}))

assert ok(request_reschedule({"appointment_id": 1, "student_id": S, "day": "Thu", "time_slot": "09:00"}))
assert not ok(respond_reschedule({"request_id": 4, "faculty_id": F2, "action": "Approved"}))

assert ok(reschedule_appointment({"appointment_id": 1, "faculty_id": F, "day": "Fri", "time_slot": "11:00"}))
assert get_appointments({"student_id": S})[0]["req_id"] is None

assert ok(cancel_appointment({"appointment_id": 1, "user_id": S}))
print("student:", kinds(S)); print("faculty:", kinds(F))
assert kinds(S)[-1] == "rescheduled" and kinds(F)[-1] == "cancelled"

n1 = len(get_notifications({"user_id": S})["notifications"]); n2 = len(get_notifications({"user_id": S})["notifications"]); assert n1 == n2

assert get_notifications({"user_id": S})["unread"] > 0
mark_read({"user_id": S}); assert get_notifications({"user_id": S})["unread"] == 0
print("ALL CHECKS PASSED")