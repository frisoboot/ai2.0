import streamlit as st
from typing import List, Dict
from datetime import datetime
import pandas as pd

from db import (
    init_db,
    fetch_questions,
    create_user,
    authenticate_user,
    start_session_db,
    save_answer_db,
    get_user_sessions_with_scores,
    get_user_progress,
)
from llm import get_feedback, generate_followup, ask_tutor

# -----------------------------
# Initialisatie
# -----------------------------
init_db()

st.set_page_config(page_title="AI Examen Trainer", page_icon="🎓", layout="wide")

st.markdown(
    """
    <style>
    .correct {color: green;}
    .incorrect {color: red;}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# State helpers
# -----------------------------


def reset_state():
    st.session_state.phase = "intro"
    st.session_state.subject = None
    st.session_state.questions = []
    st.session_state.current = 0
    st.session_state.answers = []  # list of dicts: question_id, user_answer, correct
    st.session_state.mistakes = []
    st.session_state.level = None
    st.session_state.session_id = None
    st.session_state.chat_history = []  # list of {role, content}
    # Zorg ervoor dat de fase naar intro gaat, tenzij we specifiek naar history gaan
    if st.session_state.get("phase") != "history":
        st.session_state.phase = "intro"


if "phase" not in st.session_state:
    reset_state()

# -----------------------------
# Gebruikerbeheer helpers
# -----------------------------


def logout():
    for key in list(st.session_state.keys()):
        if key != "user":
            del st.session_state[key]
    del st.session_state["user"]


# -----------------------------
# Login / registratie
# -----------------------------


if "user" not in st.session_state:
    st.title("🔐 Inloggen of registreren")
    tab1, tab2 = st.tabs(["Inloggen", "Registreren"])

    with tab1:
        u = st.text_input("Gebruikersnaam", key="login_user")
        p = st.text_input("Wachtwoord", type="password", key="login_pw")
        if st.button("Inloggen"):
            uid = authenticate_user(u, p)
            if uid:
                st.session_state.user = uid
                st.rerun()
            else:
                st.error("Combinatie onjuist.")

    with tab2:
        u2 = st.text_input("Nieuwe gebruikersnaam", key="reg_user")
        p2 = st.text_input("Kies wachtwoord", type="password", key="reg_pw")
        level_reg = st.selectbox("Kies je schoolniveau", ["mavo", "havo", "vwo"], key="reg_level")
        if st.button("Registreren"):
            succes, bericht = create_user(u2, p2, level_reg)
            if succes:
                st.success(bericht)
            else:
                st.error(bericht)

    st.stop()

# Sidebar met info & logout
with st.sidebar:
    st.markdown("### 🎓 AI Examen Trainer")
    st.markdown("---")
    st.markdown(f"👤 **{st.session_state.user['username']}**")
    st.markdown(f"📚 Niveau: **{st.session_state.user['level'].upper()}**")
    st.markdown("---")

    st.markdown("### 📋 Menu")
    if st.session_state.phase != "intro":
        if st.button("🏠 Dashboard", use_container_width=True):
            st.session_state.phase = "intro"
            st.session_state.chat_history = []  # Reset chat geschiedenis
            st.rerun()

    if st.button("📝 Oefenexamen", use_container_width=True):
        st.session_state.phase = "intro"
        st.session_state.chat_history = []  # Reset chat geschiedenis
        st.rerun()

    if st.button("💬 Tutor Chat", use_container_width=True):
        st.session_state.phase = "chat"
        st.rerun()

    if st.button("📊 Mijn Resultaten", use_container_width=True):
        st.session_state.phase = "history"
        st.rerun()

    if st.button("📈 Mijn Voortgang", use_container_width=True):
        st.session_state.phase = "progress"
        st.rerun()

    st.markdown("---")
    if st.button("🚪 Uitloggen", use_container_width=True):
        logout()
        st.rerun()

# -----------------------------
# Intro scherm
# -----------------------------
if st.session_state.phase == "intro":
    st.title("🎓 AI Examen Trainer")
    st.write("Kies een vak en start een oefenexamen. Na afloop krijg je onmiddellijke feedback én extra vragen.")

    subject = st.selectbox("Vak", ["Nederlands", "Engels", "Geschiedenis", "Economie"])

    if st.button("Start examen"):
        st.session_state.subject = subject
        st.session_state.level = st.session_state.user["level"]
        st.session_state.questions = fetch_questions(subject, st.session_state.level)
        if not st.session_state.questions:
            st.warning("Er zijn nog geen vragen voor deze combinatie beschikbaar.")
            st.stop()
        # Maak db-sessie
        sid = start_session_db(st.session_state.user["id"], subject)
        st.session_state.session_id = sid
        st.session_state.phase = "exam"
        st.rerun()

# -----------------------------
# Vragen scherm
# -----------------------------
elif st.session_state.phase == "exam":
    questions: List[Dict] = st.session_state.questions
    idx = st.session_state.current

    if idx >= len(questions):
        st.session_state.phase = "results"
        st.rerun()

    q = questions[idx]
    # Toon context indien aanwezig
    if q.get("context"):
        st.markdown(q["context"])
        st.markdown("---")  # Scheidingsteken
    st.subheader(f"Vraag {idx+1} van {len(questions)}")
    st.write(q["question"])
    # Als er een afbeelding is gekoppeld, toon deze
    if q.get("image"):
        image_path = f"data/{q['image']}"  # Voeg 'data/' toe aan het pad
        st.image(image_path, use_container_width=True)  # Gebruik use_container_width

    user_answer = None
    if q["options"]:
        user_answer = st.radio("Kies jouw antwoord:", q["options"], key=f"ans_{idx}")
    else:
        user_answer = st.text_input("Jouw antwoord:", key=f"ans_{idx}")

    if st.button("Bevestig antwoord"):
        correct = user_answer == q["correct_answer"]

        # Sla antwoord op zonder feedback
        st.session_state.answers.append(
            {
                "question": q["question"],
                "question_id": q["id"],
                "correct_answer": q["correct_answer"],
                "user_answer": user_answer,
                "is_correct": correct,
                "feedback": None,  # Feedback wordt later toegevoegd
                "image": q.get("image"),
                "context": q.get("context"),
            }
        )

        # Log naar DB zonder feedback
        if st.session_state.session_id:
            save_answer_db(
                st.session_state.session_id,
                q["id"],
                user_answer,
                correct,
                None,  # Geen feedback tijdens het examen
            )

        if not correct:
            st.session_state.mistakes.append(q["question"])
        st.session_state.current += 1
        st.rerun()

    if st.button("Examen afbreken"):
        reset_state()
        st.rerun()

# -----------------------------
# Resultaten scherm
# -----------------------------
elif st.session_state.phase == "results":
    st.header("Resultaten")
    total = len(st.session_state.answers)
    correct_cnt = sum(1 for a in st.session_state.answers if a["is_correct"])
    st.markdown(f"**Score:** {correct_cnt}/{total}")

    # Genereer feedback voor alle antwoorden
    with st.spinner("Feedback wordt gegenereerd..."):
        for a in st.session_state.answers:
            if a["feedback"] is None:  # Alleen feedback genereren als het nog niet bestaat
                feedback_text = get_feedback(
                    a["question"],
                    a["correct_answer"],
                    a["user_answer"],
                    subject=st.session_state.subject,
                    level=st.session_state.level,
                )
                a["feedback"] = feedback_text
                # Update feedback in database
                if st.session_state.session_id:
                    save_answer_db(
                        st.session_state.session_id,
                        a["question_id"],
                        a["user_answer"],
                        a["is_correct"],
                        feedback_text,
                    )

    # Voeg samenvatting toe
    st.subheader("📊 Samenvatting")
    correct_answers = [a for a in st.session_state.answers if a["is_correct"]]
    incorrect_answers = [a for a in st.session_state.answers if not a["is_correct"]]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ✅ Wat ging goed")
        if correct_answers:
            for a in correct_answers:
                st.markdown(f"- {a['question']}")
        else:
            st.markdown("*Geen correcte antwoorden*")

    with col2:
        st.markdown("### ❌ Wat kan beter")
        if incorrect_answers:
            for a in incorrect_answers:
                st.markdown(f"- {a['question']}")
        else:
            st.markdown("*Alles correct!*")

    st.markdown("---")
    for i, a in enumerate(st.session_state.answers, start=1):
        icon = "✅" if a["is_correct"] else "❌"
        cls = "correct" if a["is_correct"] else "incorrect"
        # Toon context indien aanwezig
        if a.get("context"):
            st.markdown(a["context"])
            st.markdown("---")
        st.markdown(f"**{icon} Vraag {i}:** {a['question']}")
        st.markdown(f"Jouw antwoord: <span class='{cls}'>{a['user_answer']}</span>", unsafe_allow_html=True)
        st.markdown(f"Correct antwoord: **{a['correct_answer']}**")
        if a.get("image"):
            st.image(a["image"], use_column_width=True)
        # Haal feedback op uit de opgeslagen antwoorden (indien aanwezig en niet leeg)
        feedback_to_display = a.get("feedback", "")
        if feedback_to_display:
            st.info(feedback_to_display)
        else:  # Fallback als er om een of andere reden geen feedback is opgeslagen
            fallback_feedback = get_feedback(
                a["question"],
                a["correct_answer"],
                a["user_answer"],
                subject=st.session_state.subject,
                level=st.session_state.level,
            )
            st.info(fallback_feedback)
        st.markdown("---")

    # Extra gegenereerde vragen
    extra_questions = generate_followup(
        st.session_state.subject,
        st.session_state.level,
        st.session_state.mistakes,
    )
    if extra_questions:
        st.subheader("🔄 Gepersonaliseerde vervolgvragen")
        for q in extra_questions:
            st.write(q)

    if st.button("Nieuw examen (ander vak/niveau)", key="restart_exam"):
        # enkel examen resetten, gebruiker behouden
        reset_state()
        st.rerun()

# -----------------------------
# Geschiedenis scherm
# -----------------------------
elif st.session_state.phase == "history":
    st.header("📜 Mijn Eerdere Resultaten")
    user_id = st.session_state.user["id"]
    sessions = get_user_sessions_with_scores(user_id)

    if not sessions:
        st.info("Je hebt nog geen examens gemaakt.")
    else:
        for session in sessions:
            # Formatteer de datum netjes
            try:
                # Probeer de timestamp te parsen met timezone info (indien aanwezig)
                dt_object = datetime.fromisoformat(session['started_at'])
                formatted_date = dt_object.strftime("%d-%m-%Y %H:%M")
            except ValueError:
                # Fallback voor oudere sqlite versies die geen timezone info opslaan
                try:
                    dt_object = datetime.strptime(session['started_at'].split('.')[0], "%Y-%m-%d %H:%M:%S")
                    formatted_date = dt_object.strftime("%d-%m-%Y %H:%M")
                except:
                    formatted_date = session['started_at']  # Fallback to raw string

            score = f"{session['correct_answers']}/{session['total_questions']}"
            st.subheader(f"Examen: {session['subject']}")
            st.write(f"Datum: {formatted_date}")
            st.write(f"Score: {score}")
            st.markdown("---")

# -----------------------------
# Tutor Chat scherm
# -----------------------------
elif st.session_state.phase == "chat":
    st.header("💬 Tutor Chat")

    subject = st.selectbox("Vak", ["Nederlands", "Engels", "Geschiedenis", "Economie"], key="chat_subject")

    # Voeg knop toe om door te gaan met oefenen op basis van laatste examen
    if st.session_state.get("answers"):
        if st.button("📚 Ga verder met oefenen op basis van laatste examen"):
            # Maak een samenvatting van de fouten
            mistakes = [a["question"] for a in st.session_state.answers if not a["is_correct"]]
            if mistakes:
                # Voeg een systeem bericht toe met de context
                context_message = (
                    f"Je hebt net een {st.session_state.subject} examen gemaakt op {st.session_state.level} niveau. "
                    f"Je had moeite met de volgende onderwerpen:\n" +
                    "\n".join(f"- {m}" for m in mistakes) +
                    "\n\nLaten we hier verder op oefenen. Stel gerust vragen over deze onderwerpen!"
                )
                st.session_state.chat_history.append({"role": "assistant", "content": context_message})
                st.rerun()
            else:
                st.success("Gefeliciteerd! Je had geen fouten in je laatste examen.")

    # Toon bestaande geschiedenis
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Stel je vraag:", key="chat_input")

    if user_input and user_input.strip():
        # Voeg user message toe aan history
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        # Vraag response aan LLM
        response = ask_tutor(
            subject=subject,
            level=st.session_state.user["level"],
            user_question=user_input,
            history=st.session_state.chat_history,
        )
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.rerun()

# -----------------------------
# Voortgang Dashboard scherm
# -----------------------------
elif st.session_state.phase == "progress":
    st.header("📈 Mijn Voortgang per Vak")

    # Haal voortgang op
    progress = get_user_progress(st.session_state.user["id"])

    if not progress:
        st.info("Je hebt nog geen examens gemaakt. Start een examen om je voortgang te zien!")
    else:
        # Groepeer voortgang per vak
        subjects = {}
        for p in progress:
            if p["subject"] not in subjects:
                subjects[p["subject"]] = []
            subjects[p["subject"]].append(p)

        # Toon voortgang per vak
        for subject, topics in subjects.items():
            st.subheader(f"📚 {subject}")

            # Maak een DataFrame voor de visualisatie
            df = pd.DataFrame(topics)

            # Toon voortgang per onderwerp
            for topic in topics:
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**{topic['topic']}**")
                with col2:
                    st.write(f"Score: {topic['correct_answers']}/{topic['total_questions']}")
                with col3:
                    # Kleur op basis van percentage
                    color = "green" if topic['percentage'] >= 70 else "orange" if topic['percentage'] >= 50 else "red"
                    st.markdown(f"<span style='color: {color}'>{topic['percentage']}%</span>", unsafe_allow_html=True)

                # Voeg een voortgangsbalk toe
                st.progress(topic['percentage'] / 100)

            st.markdown("---")

        # Voeg aanbevelingen toe
        st.subheader("🎯 Aanbevelingen")
        weak_topics = [t for t in progress if t['percentage'] < 70]
        if weak_topics:
            st.write("Focus op deze onderwerpen om je score te verbeteren:")
            for topic in weak_topics:
                st.write(f"- {topic['subject']}: {topic['topic']} ({topic['percentage']}%)")
        else:
            st.success("Geweldig! Je scoort goed op alle onderwerpen!")
