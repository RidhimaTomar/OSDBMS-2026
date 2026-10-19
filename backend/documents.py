import base64
import binascii
import mimetypes
import os
import re
import secrets

from database import get_connection
from notifications import notify

UPLOAD_DIR = os.environ.get("CAMPUS_UPLOADS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uploads")

MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
           ".txt", ".md", ".png", ".jpg", ".jpeg", ".zip"}
UPLOADERS = ("Faculty")


def _user(con, user_id):
    return con.execute("SELECT user_id, name, role FROM users WHERE user_id=?",
                       (user_id,)).fetchone()


def _clean_name(name):
    """Keep only the file name part and strip risky characters."""
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    return re.sub(r"[^A-Za-z0-9._ ()\-]", "_", name)[:120]


def upload_document(data):
    con = get_connection()
    try:
        user = _user(con, data.get("user_id"))
        if user is None or user["role"] not in UPLOADERS:
            return {"success": False, "message": "Only faculty or admin can upload documents"}

        title = (data.get("title") or "").strip()
        filename = _clean_name(data.get("filename"))
        ext = os.path.splitext(filename)[1].lower()

        if not title:
            return {"success": False, "message": "Give the document a title"}
        if not filename or ext not in ALLOWED:
            return {"success": False,
                    "message": "File type not allowed. Use " + ", ".join(sorted(ALLOWED))}

        try:
            raw = base64.b64decode(data.get("data") or "", validate=True)
        except (binascii.Error, ValueError):
            return {"success": False, "message": "The file could not be read"}

        if not raw:
            return {"success": False, "message": "The file is empty"}
        if len(raw) > MAX_BYTES:
            return {"success": False, "message": "File is larger than 10 MB"}

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        stored = secrets.token_hex(16) + ext
        path = os.path.join(UPLOAD_DIR, stored)
        with open(path, "wb") as f:
            f.write(raw)

        try:
            cur = con.execute("""
                INSERT INTO documents
                (uploader_id, title, subject, description, filename, stored_name, mime_type, size_bytes)
                VALUES (?,?,?,?,?,?,?,?)
            """, (user["user_id"], title[:150], (data.get("subject") or "").strip()[:80],
                  (data.get("description") or "").strip()[:500], filename, stored,
                  mimetypes.guess_type(filename)[0] or "application/octet-stream", len(raw)))

            notify(con, user["user_id"], "document",
                   f"Your document \"{title[:150]}\" was uploaded successfully")
            for s in con.execute("SELECT user_id FROM users WHERE role='Student'").fetchall():
                notify(con, s["user_id"], "document",
                       f"{user['name']} shared a new document: {title[:150]}")
            con.commit()
        except Exception:
            con.rollback()
            os.remove(path)  # do not leave a file behind without a database row
            raise

        return {"success": True, "message": "Document uploaded", "document_id": cur.lastrowid}
    finally:
        con.close()


def get_documents(params):
    con = get_connection()
    try:
        if _user(con, params.get("user_id")) is None:
            return {"success": False, "message": "Please log in"}

        sql = """
            SELECT d.document_id, d.title, d.subject, d.description, d.filename,
                   d.size_bytes, d.uploaded_at, d.uploader_id, u.name AS uploader
            FROM documents d JOIN users u ON d.uploader_id = u.user_id
            WHERE 1=1
        """
        args = []
        q = (params.get("q") or "").strip()
        if q:
            sql += " AND (d.title LIKE ? OR d.subject LIKE ? OR d.description LIKE ? OR u.name LIKE ?)"
            args += ["%" + q + "%"] * 4
        if params.get("uploader_id"):
            sql += " AND d.uploader_id=?"
            args.append(params["uploader_id"])
        sql += " ORDER BY d.document_id DESC"

        rows = con.execute(sql, args).fetchall()
        return {"success": True, "documents": [dict(r) for r in rows]}
    finally:
        con.close()


def get_download(params):
    """Return (filename, mime_type, bytes) or None. Used by the server for binary replies."""
    con = get_connection()
    try:
        if _user(con, params.get("user_id")) is None:
            return None
        row = con.execute("SELECT filename, stored_name, mime_type FROM documents WHERE document_id=?",
                          (params.get("document_id"),)).fetchone()
    finally:
        con.close()

    if row is None:
        return None
    path = os.path.realpath(os.path.join(UPLOAD_DIR, row["stored_name"]))
    if not path.startswith(os.path.realpath(UPLOAD_DIR) + os.sep) or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return row["filename"], row["mime_type"], f.read()


def remove_files(stored_names):
    for name in stored_names:
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


def delete_document(data):
    con = get_connection()
    try:
        user = _user(con, data.get("user_id"))
        doc = con.execute("SELECT uploader_id, stored_name FROM documents WHERE document_id=?",
                          (data.get("document_id"),)).fetchone()
        if user is None or doc is None:
            return {"success": False, "message": "Document not found"}
        if user["role"] != "Admin" and doc["uploader_id"] != user["user_id"]:
            return {"success": False, "message": "You can only delete your own documents"}

        con.execute("DELETE FROM documents WHERE document_id=?", (data.get("document_id"),))
        con.commit()
    finally:
        con.close()

    remove_files([doc["stored_name"]])
    return {"success": True, "message": "Document deleted"}

