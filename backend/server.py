from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import mimetypes
import os

from database import init_db
from auth import login
from users import add_user, get_users, delete_user, get_faculty
from timetable import add_timetable, get_timetable, check_conflict, delete_timetable
from appointments import (
    book_appointment, get_appointments, cancel_appointment,
    get_availability, respond_appointment, reschedule_appointment
)
from reschedule import request_reschedule, respond_reschedule, withdraw_reschedule
from notifications import get_notifications, mark_read
from calendar_view import get_calendar
from os_engine.fcfs import fcfs
from os_engine.priority import priority_scheduling
from os_engine.round_robin import round_robin
from os_engine.synchronization import try_booking
from os_engine.deadlock import deadlock_check
from os_engine.memory import fifo, lru, optimal
from os_engine.disk import disk_fcfs, sstf, scan

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8000))
FRONTEND_DIR = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
)

GET_ROUTES = {
    "/api/admin/users": get_users,
    "/api/faculty": lambda q: get_faculty(),
    "/api/timetable": lambda q: get_timetable(),
    "/api/appointments": get_appointments,
    "/api/availability": get_availability,
    "/api/notifications": get_notifications,
    "/api/calendar": get_calendar,
}

POST_ROUTES = {
    "/api/login": login,
    "/api/admin/users": add_user,
    "/api/timetable": add_timetable,
    "/api/timetable/check-conflict": check_conflict,
    "/api/appointments": book_appointment,
    "/api/appointments/cancel": cancel_appointment,
    "/api/appointments/respond": respond_appointment,
    "/api/appointments/reschedule": reschedule_appointment,
    "/api/appointments/reschedule-request": request_reschedule,
    "/api/appointments/reschedule-respond": respond_reschedule,
    "/api/appointments/reschedule-withdraw": withdraw_reschedule,
    "/api/notifications/read": mark_read,

    "/api/os/fcfs": lambda d: fcfs(d["burst_time"]),
    "/api/os/priority": lambda d: priority_scheduling(d["burst_time"], d["priority"]),
    "/api/os/round-robin": lambda d: round_robin(d["burst_time"], d["quantum"]),

    "/api/os/synchronization": lambda d: try_booking(d["slot"]),

    "/api/os/deadlock": lambda d: deadlock_check(d["allocation"], d["request"]),

    "/api/os/memory/fifo": lambda d: fifo(d["pages"], d["frames"]),
    "/api/os/memory/lru": lambda d: lru(d["pages"], d["frames"]),
    "/api/os/memory/optimal": lambda d: optimal(d["pages"], d["frames"]),

    "/api/os/disk/fcfs": lambda d: disk_fcfs(d["requests"], d["head"]),
    "/api/os/disk/sstf": lambda d: sstf(d["requests"], d["head"]),
    "/api/os/disk/scan": lambda d: scan(d["requests"], d["head"], d["disk_size"]),
}

DELETE_ROUTES = {
    "/api/admin/users": delete_user,
    "/api/timetable": delete_timetable,
}

class Handler(BaseHTTPRequestHandler):

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def send_static(self, path):

        name = "index.html" if path == "/" else path.lstrip("/")
        full = os.path.realpath(os.path.join(FRONTEND_DIR, name))

        if not full.startswith(FRONTEND_DIR) or not os.path.isfile(full):
            self.send_json({"success": False, "message": "Not found"}, 404)
            return

        with open(full, "rb") as f:
            body = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self, routes, arg):
        path = urlparse(self.path).path
        if path in routes:
            self.send_json(routes[path](arg))
        else:
            self.send_json({"success": False, "message": "API not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.cors()
        self.end_headers()

      
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                self.handle_api(GET_ROUTES, query)
            else:
                self.send_static(parsed.path)
        except Exception as e:
            self.send_json({"success": False, "message": str(e)}, 500)
            
    def do_POST(self):
        try:
            self.handle_api(POST_ROUTES, self.read_json())
        except Exception as e:
            self.send_json({"success": False, "message": str(e)}, 500)

    def do_DELETE(self):
        try:
            self.handle_api(DELETE_ROUTES, self.read_json())
        except Exception as e:
            self.send_json({"success": False, "message": str(e)}, 500)

    def log_message(self, fmt, *args):
            super().log_message(fmt, *args)

if __name__ == "__main__":
    print("Initializing database...", flush=True)
    init_db()
    print(f"CampusSync running on port {PORT}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()
