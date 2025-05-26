import sqlite3
import json
import os
from pathlib import Path
from typing import List, Dict
import hashlib

DB_PATH = Path(__file__).with_suffix(".db")

# ---------------------------
# Database helpers
# ---------------------------


def get_connection():
    """Return a SQLite connection (auto-connects to DB_PATH)."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Initialiseer de database en importeer (externe) JSON-vragen indien aanwezig."""
    conn = get_connection()
    cur = conn.cursor()

    # Tabellen aanmaken
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            level TEXT NOT NULL,
            year INTEGER NOT NULL,
            question TEXT NOT NULL,
            options TEXT,              -- JSON-array van opties (of NULL voor open vraag)
            correct_answer TEXT NOT NULL,
            image TEXT,                -- Pad naar afbeelding (of NULL)
            context TEXT               -- Inleidende tekst (of NULL)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'havo'
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            question_id INTEGER,
            user_answer TEXT,
            is_correct INTEGER,
            feedback TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id),
            FOREIGN KEY(question_id) REFERENCES questions(id)
        );
        """
    )

    conn.commit()

    # --- schema upgrades ---
    # questions.level
    cur.execute("PRAGMA table_info(questions)")
    cols = [row[1] for row in cur.fetchall()]
    if "level" not in cols:
        cur.execute("ALTER TABLE questions ADD COLUMN level TEXT DEFAULT 'havo'")

    # sessions.user_id
    cur.execute("PRAGMA table_info(sessions)")
    s_cols = [row[1] for row in cur.fetchall()]
    if "user_id" not in s_cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER")

    # users.level
    cur.execute("PRAGMA table_info(users)")
    u_cols = [row[1] for row in cur.fetchall()]
    if "level" not in u_cols:
        cur.execute("ALTER TABLE users ADD COLUMN level TEXT NOT NULL DEFAULT 'havo'")

    # Importeer externe vragenbestanden (./data/*.json)
    import_json_questions(cur)

    conn.close()


def fetch_questions(subject: str, level: str) -> List[Dict]:
    """Haal alle vragen op voor een vak + niveau (mavo/havo/vwo)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, question, options, correct_answer, image, context FROM questions WHERE subject = ? AND level = ? ORDER BY id",
        (subject, level),
    )
    rows = cur.fetchall()
    conn.close()

    questions = []
    for rid, question, options_json, correct, image, context in rows:
        options = json.loads(options_json) if options_json else None
        questions.append(
            {
                "id": rid,
                "question": question,
                "options": options,
                "correct_answer": correct,
                "image": image,
                "context": context,
            }
        )
    return questions


def import_json_questions(cur):
    """Importeer vragen uit ./data/*.json (bestandsnaam: <subject>_<level>.json)."""
    data_dir = Path(__file__).with_name("data")
    if not data_dir.exists():
        return

    # Verwijder eerst alle bestaande vragen
    cur.execute("DELETE FROM questions")

    for path in data_dir.glob("*.json"):
        parts = path.stem.split("_")
        if len(parts) != 2:
            continue
        raw_subject, level = parts
        # normaliseer subject
        subject_map = {"eco": "Economie", "economie": "Economie", "geschiedenis": "Geschiedenis", "nederlands": "Nederlands", "engels": "Engels"}
        subject = subject_map.get(raw_subject.lower(), raw_subject.capitalize())
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception as e:
            print(f"Fout bij laden van {path}: {e}")
            continue

        for item in items:
            question = item.get("question")
            options = item.get("options")
            correct = item.get("correct_answer")
            item_level = item.get("level") or level
            context = item.get("context")
            image = item.get("image")

            if not question or not correct or not item_level:
                continue

            cur.execute(
                """INSERT INTO questions(subject, level, year, question, options, correct_answer, image, context)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    subject,
                    item_level.lower(),
                    0,  # onbekend jaar
                    question,
                    json.dumps(options) if options else None,
                    correct,
                    image,
                    context,
                ),
            )
    # commit via connection
    cur.connection.commit()


# ---------------------------
# Gebruiker-management
# ---------------------------


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user(username: str, password: str, level: str) -> tuple[bool, str]:
    """Maak een nieuwe gebruiker. Return (succes, bericht).

    Deze functie controleert dynamisch of de kolom `salt` aanwezig is in de
    tabel `users`.  Bestaat die kolom, dan wordt een willekeurig salt
    gegenereerd en wordt het wachtwoord gehasht als `sha256(password+salt)`.
    Bestaat de kolom niet, dan wordt het wachtwoord gehasht zonder salt (oude
    schema)."""

    conn = get_connection()
    cur = conn.cursor()

    # Bepaal kolommen in users-tabel (cached per call is prima)
    cur.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in cur.fetchall()]

    use_salt = "salt" in user_cols

    # Genereer hash (+ optional salt)
    if use_salt:
        salt = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        pw_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    else:
        salt = None
        pw_hash = _hash_pw(password)

    try:
        if use_salt:
            cur.execute(
                "INSERT INTO users(username, password, salt, level) VALUES(?, ?, ?, ?)",
                (username.strip(), pw_hash, salt, level),
            )
        else:
            cur.execute(
                "INSERT INTO users(username, password, level) VALUES(?, ?, ?)",
                (username.strip(), pw_hash, level),
            )

        conn.commit()
        return True, "Gebruiker succesvol aangemaakt"

    except sqlite3.IntegrityError as e:
        # Unieke constraint of andere integriteitsfout? Geef nuttige feedback.
        msg = str(e).lower()
        if "unique" in msg or "constraint" in msg:
            return False, "Deze gebruikersnaam bestaat al"
        return False, f"Fout bij registreren gebruiker: {e}"

    finally:
        conn.close()


def authenticate_user(username: str, password: str):
    """Return gebruiker-info dict indien inlog klopt, anders None.

    Ondersteunt zowel het oude schema (zonder salt) als het nieuwe schema
    (met salt-kolom)."""

    conn = get_connection()
    cur = conn.cursor()

    # Bepaal of salt-kolom aanwezig is
    cur.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in cur.fetchall()]

    has_salt = "salt" in user_cols

    if has_salt:
        # Haal salt & hash op en vergelijk in Python
        cur.execute(
            "SELECT id, username, level, salt, password FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        uid, uname, lvl, salt, stored_hash = row
        pw_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        conn.close()
        if pw_hash == stored_hash:
            return {"id": uid, "username": uname, "level": lvl}
        return None

    else:
        # Oud schema zonder salt
        cur.execute(
            "SELECT id, username, level FROM users WHERE username = ? AND password = ?",
            (username.strip(), _hash_pw(password)),
        )
        row = cur.fetchone()
        conn.close()
        return {"id": row[0], "username": row[1], "level": row[2]} if row else None


# ---------------------------
# Sessie- en antwoordlog
# ---------------------------


def start_session_db(user_id: int, subject: str) -> int:
    """Maak een sessie aan en return ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions(user_id, subject) VALUES(?, ?)",
        (user_id, subject),
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def save_answer_db(session_id: int, question_id: int, user_answer: str, is_correct: bool, feedback: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO answers(session_id, question_id, user_answer, is_correct, feedback)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, question_id, user_answer, int(is_correct), feedback),
    )
    conn.commit()
    conn.close()


def get_user_sessions_with_scores(user_id: int) -> List[Dict]:
    """Haal alle sessies van een gebruiker op met scores."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            s.id AS session_id,
            s.subject,
            s.started_at,
            COUNT(a.id) AS total_questions,
            SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_answers
        FROM sessions s
        JOIN answers a ON s.id = a.session_id
        WHERE s.user_id = ?
        GROUP BY s.id, s.subject, s.started_at
        ORDER BY s.started_at DESC
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()

    sessions_data = []
    for row in rows:
        sessions_data.append({
            "session_id": row[0],
            "subject": row[1],
            "started_at": row[2],
            "total_questions": row[3],
            "correct_answers": row[4] if row[4] is not None else 0,  # Zorg voor 0 als er geen correcte antwoorden zijn
        })
    return sessions_data


def get_user_progress(user_id: int) -> List[Dict]:
    """Haal de voortgang van een gebruiker op per vak en onderwerp."""
    conn = get_connection()
    cursor = conn.cursor()

    # Haal alle sessies van de gebruiker op met hun scores per onderwerp
    cursor.execute("""
        SELECT 
            s.subject,
            q.topic,
            COUNT(*) as total_questions,
            SUM(CASE WHEN a.is_correct THEN 1 ELSE 0 END) as correct_answers
        FROM sessions s
        JOIN answers a ON s.id = a.session_id
        JOIN questions q ON a.question_id = q.id
        WHERE s.user_id = ?
        GROUP BY s.subject, q.topic
        ORDER BY s.subject, q.topic
    """, (user_id,))

    progress = []
    for row in cursor.fetchall():
        progress.append({
            "subject": row[0],
            "topic": row[1],
            "total_questions": row[2],
            "correct_answers": row[3],
            "percentage": round((row[3] / row[2]) * 100) if row[2] > 0 else 0
        })

    conn.close()
    return progress
