import sqlite3
from security import hash_password, is_hashed

DB_NAME = "campus.db"


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
        CREATE UNIQUE INDEX IF NOT EXISTS uq_room_slot
        ON timetable(room, day, time_slot)
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

    
    for row in cur.execute("SELECT user_id, password FROM users").fetchall():
        if not is_hashed(row["password"]):
            con.execute(
                "UPDATE users SET password=? WHERE user_id=?",
                (hash_password(row["password"]), row["user_id"])
            )

    con.commit()
    con.close()
