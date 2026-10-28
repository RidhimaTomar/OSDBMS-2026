import os
import sqlite3
from security import hash_password, is_hashed

DB_NAME = os.environ.get("CAMPUS_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus.db")

def get_connection():
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def init_db():
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    # Faculty office location (older databases get the column added in place).
    cols = [r["name"] for r in cur.execute("PRAGMA table_info(users)")]
    if "office" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN office TEXT DEFAULT ''")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            day TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            room TEXT NOT NULL,
            FOREIGN KEY (faculty_id) REFERENCES users(user_id),
            UNIQUE(faculty_id, day, time_slot)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            faculty_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            topic TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY (student_id) REFERENCES users(user_id),
            FOREIGN KEY (faculty_id) REFERENCES users(user_id)
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_slot
        ON appointments(faculty_id, day, time_slot)
        WHERE status IN ('Pending', 'Accepted', 'Rescheduled')
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reschedule_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            requested_by INTEGER NOT NULL,
            new_day TEXT NOT NULL,
            new_time_slot TEXT NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id),
            FOREIGN KEY (requested_by) REFERENCES users(user_id)
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_open_reschedule
        ON reschedule_requests(appointment_id) WHERE status = 'Pending'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            appointment_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            dedupe_key TEXT UNIQUE,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notif_user
        ON notifications(user_id, is_read, notification_id)
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_room_slot
        ON timetable(room, day, time_slot)
    """)

    # ---- Venues (where a meeting takes place) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS venues (
            venue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            location TEXT DEFAULT '',
            capacity INTEGER DEFAULT 1 CHECK (capacity > 0)
        )
    """)

    # Older databases have no venue column on appointments: add it in place.
    cols = [r["name"] for r in cur.execute("PRAGMA table_info(appointments)")]
    if "venue_id" not in cols:
        cur.execute("ALTER TABLE appointments ADD COLUMN venue_id INTEGER REFERENCES venues(venue_id)")

    # The meeting place is now free text typed by the faculty (e.g. "my office", "Room 204").
    if "venue" not in cols:
        cur.execute("ALTER TABLE appointments ADD COLUMN venue TEXT DEFAULT ''")
        # Keep the place of meetings that were booked with the old venue list.
        cur.execute("""UPDATE appointments
                       SET venue=(SELECT name FROM venues WHERE venues.venue_id=appointments.venue_id)
                       WHERE venue_id IS NOT NULL""")

    # One venue can host only one active meeting at a given day + time.
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_venue_slot
        ON appointments(venue_id, day, time_slot)
        WHERE venue_id IS NOT NULL AND status IN ('Pending', 'Accepted', 'Rescheduled')
    """)

    # ---- Shared documents / notes ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id INTEGER PRIMARY KEY AUTOINCREMENT,
            uploader_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subject TEXT DEFAULT '',
            description TEXT DEFAULT '',
            filename TEXT NOT NULL,
            stored_name TEXT UNIQUE NOT NULL,
            mime_type TEXT DEFAULT 'application/octet-stream',
            size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploader_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploader_id)")

    # ---- Student/faculty direct chat ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            message TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 2000),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sender_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (recipient_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_pair ON chat_messages(sender_id, recipient_id, message_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_inbox ON chat_messages(recipient_id, is_read, message_id)")

    # ---- Faculty invitations (admin invites by email, faculty registers via link) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            invitation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT DEFAULT '',
            token_hash TEXT UNIQUE NOT NULL,
            invited_by INTEGER NOT NULL,
            status TEXT DEFAULT 'Pending' CHECK (status IN ('Pending', 'Accepted', 'Revoked')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (invited_by) REFERENCES users(user_id)
        )
    """)
    # At most one live invitation per email.
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_invite
        ON invitations(email) WHERE status = 'Pending'
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS faculty_schedule AS
        SELECT timetable.timetable_id, users.name AS faculty,
               timetable.subject, timetable.day,
               timetable.time_slot, timetable.room
        FROM timetable
        JOIN users ON timetable.faculty_id = users.user_id
    """)

    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS appointment_cancel_check
        AFTER UPDATE OF status ON appointments
        WHEN NEW.status = 'Cancelled'
        BEGIN
            UPDATE appointments
            SET status = 'Cancelled'
            WHERE appointment_id = NEW.appointment_id;
        END
    """)

    con.commit()

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Admin", "admin@campussync.com", hash_password("admin123"), "Admin")
        )
        cur.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Dr. Sharma", "faculty@campussync.com", hash_password("faculty123"), "Faculty")
        )
        cur.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Student", "student@campussync.com", hash_password("student123"), "Student")
        )
        cur.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            ("Prof. Rao", "rao@campussync.com", hash_password("faculty123"), "Faculty")
        )

        for row in [
            (2, "DBMS", "Mon", "09:00", "204"),
            (2, "DBMS Lab", "Mon", "10:00", "Lab 3"),
            (2, "Operating Systems", "Tue", "11:00", "110"),
            (4, "Networks", "Mon", "11:00", "305"),
            (4, "AI", "Wed", "09:00", "210"),
        ]:
            cur.execute(
                "INSERT INTO timetable(faculty_id,subject,day,time_slot,room) "
                "VALUES(?,?,?,?,?)", row
            )

    con.commit()

    if cur.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 0:
        for v in [
            ("Faculty Cabin", "Staff block, 1st floor", 3),
            ("Meeting Room 1", "Admin block, ground floor", 8),
            ("Meeting Room 2", "Admin block, ground floor", 8),
            ("Library Discussion Room", "Library, 2nd floor", 6),
            ("Seminar Hall", "Main building", 40),
        ]:
            cur.execute("INSERT INTO venues(name,location,capacity) VALUES(?,?,?)", v)
    con.commit()

    for row in cur.execute("SELECT user_id, password FROM users").fetchall():
        if not is_hashed(row["password"]):
            con.execute(
                "UPDATE users SET password=? WHERE user_id=?",
                (hash_password(row["password"]), row["user_id"])
            )

    con.commit()
    con.close()
