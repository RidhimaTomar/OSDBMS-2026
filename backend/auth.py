from database import get_connection
from security import verify_password


def login(data):
    email = data.get("email")
    password = data.get("password") or ""

    con = get_connection()
    row = con.execute(
        "SELECT user_id, name, role, password FROM users WHERE email=?",
        (email,)
    ).fetchone()
    con.close()

    if row and verify_password(password, row["password"]):
        return {
            "success": True,
            "user_id": row["user_id"],
            "name": row["name"],
            "role": row["role"]
        }

    return {
        "success": False,
        "message": "Invalid email or password"
    }
