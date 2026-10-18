from database import get_connection
from security import hash_password


def is_admin(user_id):
    con = get_connection()
    row = con.execute(
        "SELECT role FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()

    return row is not None and row["role"] == "Admin"


def add_user(data):
    admin_id = data.get("admin_id")
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    office = (data.get("office") or "").strip()

    if not is_admin(admin_id):
        return {"success": False, "message": "Only admin can add users"}

    if not name or not email or not password or role not in ["Faculty", "Student"]:
        return {
            "success": False,
            "message": "Name, email, password and valid role are required"
        }

    con = get_connection()

    try:
        con.execute(
            "INSERT INTO users(name, email, password, role, office) VALUES(?,?,?,?,?)",
            (name, email, hash_password(password), role, office if role == "Faculty" else "")
        )
        con.commit()
        return {
            "success": True,
            "message": role + " added successfully"
        }
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return {"success": False, "message": "Email already exists"}
        return {"success": False, "message": str(e)}
    finally:
        con.close()


def get_users(data):
    admin_id = data.get("admin_id")

    if not is_admin(admin_id):
        return {"success": False, "message": "Only admin can view users"}

    con = get_connection()
    rows = con.execute(
        "SELECT user_id, name, email, role FROM users "
        "WHERE role IN ('Faculty', 'Student') ORDER BY role, name"
    ).fetchall()
    con.close()

    users = []
    for row in rows:
        users.append(dict(row))

    return {"success": True, "users": users}


def delete_user(data):
    admin_id = data.get("admin_id")
    user_id = data.get("user_id")

    if not is_admin(admin_id):
        return {"success": False, "message": "Only admin can delete users"}

    con = get_connection()

    row = con.execute(
        "SELECT role FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()

    if row is None:
        con.close()
        return {"success": False, "message": "User not found"}

    if row["role"] == "Admin":
        con.close()
        return {"success": False, "message": "Admin cannot be deleted"}

    try:
        from documents import remove_files
        files = [r["stored_name"] for r in con.execute(
            "SELECT stored_name FROM documents WHERE uploader_id=?", (user_id,))]
        con.execute("DELETE FROM timetable WHERE faculty_id=?", (user_id,))
        # Child rows first, otherwise the foreign keys block the delete.
        con.execute("""DELETE FROM reschedule_requests WHERE requested_by=? OR appointment_id IN
                       (SELECT appointment_id FROM appointments WHERE student_id=? OR faculty_id=?)""",
                    (user_id, user_id, user_id))
        con.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM appointments WHERE student_id=? OR faculty_id=?", (user_id, user_id))
        con.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        con.commit()
        remove_files(files)
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        con.rollback()
        return {"success": False, "message": str(e)}
    finally:
        con.close()


def set_faculty_office(data):
    if not is_admin(data.get("admin_id")):
        return {"success": False, "message": "Only admin can set faculty offices"}
    con = get_connection()
    try:
        cur = con.execute("UPDATE users SET office=? WHERE user_id=? AND role='Faculty'",
                          ((data.get("office") or "").strip(), data.get("faculty_id")))
        con.commit()
        if not cur.rowcount:
            return {"success": False, "message": "Faculty not found"}
        return {"success": True, "message": "Office updated"}
    finally:
        con.close()


def get_faculty():
    # Public list so students can choose whom to meet (includes office location).
    con = get_connection()
    rows = con.execute(
        "SELECT user_id, name, office FROM users WHERE role='Faculty' ORDER BY name"
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]