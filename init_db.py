import sqlite3
import hashlib
import os


def init_db():
    # Verwijder bestaande database als die bestaat
    if os.path.exists('db.db'):
        os.remove('db.db')

    # Maak nieuwe database connectie
    conn = sqlite3.connect('db.db')
    c = conn.cursor()

    # Maak users tabel
    c.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        salt TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'havo',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Maak questions tabel
    c.execute('''
    CREATE TABLE questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        level TEXT NOT NULL,
        year INTEGER NOT NULL,
        question TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        options TEXT,
        context TEXT,
        image TEXT,
        topic TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Maak question_options tabel
    c.execute('''
    CREATE TABLE question_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        option_text TEXT NOT NULL,
        option_order INTEGER NOT NULL,
        FOREIGN KEY(question_id) REFERENCES questions(id)
    )
    ''')

    # Maak sessions tabel
    c.execute('''
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')

    # Maak answers tabel
    c.execute('''
    CREATE TABLE answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        user_answer TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES sessions(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    )
    ''')

    # Maak indexes
    c.execute('CREATE INDEX idx_questions_subject ON questions(subject)')
    c.execute('CREATE INDEX idx_questions_level ON questions(level)')
    c.execute('CREATE INDEX idx_answers_session ON answers(session_id)')
    c.execute('CREATE INDEX idx_answers_question ON answers(question_id)')

    # Voeg test gebruiker toe
    salt = 'salt123'
    password = 'test123'
    hashed_password = hashlib.sha256((password + salt).encode()).hexdigest()

    c.execute('''
    INSERT INTO users (username, password, salt, level)
    VALUES (?, ?, ?, ?)
    ''', ('friso', hashed_password, salt, 'vwo'))

    # Voeg test vragen toe
    questions = [
        ('Economie', 'vwo', 2023, 'Verklaar of Tradesure rekening moet houden met moral hazard bij het afsluiten van exportverzekeringen.',
         'Ja: nadat exporteurs verzekerd zijn tegen valutarisico\'s, kunnen ze minder zorgvuldig omgaan met het afdekken van hun risico\'s (moral hazard). Dit verhoogt het risico voor de verzekeraar.'),
        ('Economie', 'vwo', 2023, 'Leg uit dat een positief overheidssaldo via de begroting kan bijdragen aan lagere rentes op de kapitaalmarkt.',
         'Een overschot betekent dat de staat meer geld inlevert dan uitgeeft. Hierdoor daalt de overheidsschuld, wat de vraag naar leningen vermindert en de rente op de kapitaalmarkt omlaag brengt.'),
        ('Economie', 'vwo', 2023, 'Leg uit dat een verhoging van de inkomstenbelasting de economische groei kan remmen.',
         'Hogere inkomstenbelasting verlaagt de prikkel om te werken of te investeren. Daardoor neemt de arbeidsparticipatie en kapitaalinvestering af, wat de economische groei afremt.'),
        ('Economie', 'vwo', 2023, 'Leg met behulp van de kruislingse prijselasticiteit van de vraag uit of producten A en B substituten of complementen zijn.',
         'Als de kruislingse prijselasticiteit positief is, stijgt de vraag naar B als de prijs van A stijgt: dat zijn substituten. Is de elasticiteit negatief, dan zijn het complementen.'),
        ('Economie', 'vwo', 2023, 'Leg uit dat de productie van product A leidt tot een welvaartsverlies voor de samenleving.',
         'Bij de productie van A ontstaat vervuiling die niet in de prijs zit. Dit is een negatief extern effect. De maatschappelijke kosten zijn hoger dan de private kosten. Daardoor is de marktuitkomst niet efficiënt, wat leidt tot welvaartsverlies.')
    ]

    c.executemany('''
    INSERT INTO questions (subject, level, year, question, correct_answer)
    VALUES (?, ?, ?, ?, ?)
    ''', questions)

    # Commit changes en sluit connectie
    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    print("Database succesvol geïnitialiseerd!")
