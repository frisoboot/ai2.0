import os
from typing import List

try:
    from openai import OpenAI
except ImportError:  # indien requirements nog niet geïnstalleerd
    OpenAI = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# -------------
# Config
# -------------

def _openai_available() -> bool:
    return OpenAI is not None and os.getenv("OPENAI_API_KEY")


# -------------
# Public API
# -------------

def get_feedback(question_text: str, correct_answer: str, user_answer: str, *, subject: str, level: str, language: str = "nl") -> str:
    """Geef feedback op basis van GPT. Valt terug op een simpele string zonder API-key."""
    if not _openai_available():
        return (
            "AI-feedback niet beschikbaar (geen API-key). Juiste antwoord is "
            f"'{correct_answer}'."
        )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_msg = (
        "Je bent een behulpzame docent {}-docent op {} niveau. "
        "Leg kort (max 2 zinnen, {} taal) uit waarom het antwoord juist of onjuist is en geef een tip.".format(subject, level.upper(), language)
    )
    user_prompt = (
        f"Vraag: {question_text}\n"
        f"Antwoord leerling: {user_answer}\n"
        f"Correcte antwoord: {correct_answer}\n"
        "Geef feedback:"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=100,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(Fout bij ophalen AI-feedback: {e}) Juiste antwoord: '{correct_answer}'."


def generate_followup(subject: str, level: str, mistakes: List[str], n: int = 3) -> List[str]:
    """Genereer n nieuwe vragen van hetzelfde vak gebaseerd op fouten. Returnt lijst string-vragen."""
    if not _openai_available() or not mistakes:
        return []

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_msg = (
        "Je bent een examenmaker voor het vak {} (niveau {}). Schrijf {} nieuwe examenvragen gebaseerd op deze fouten. "
        "Elke vraag moet een korte multiple-choice vraag zijn met 4 opties (A-D) en geef het correcte antwoord apart."
    ).format(subject, level.upper(), n)
    user_prompt = "Fouten/onderwerpen: " + "; ".join(mistakes)

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.8,
        )
        return [response.choices[0].message.content.strip()]
    except Exception as e:
        return [f"(Fout bij genereren vragen: {e})"]


# -----------------------------
# Tutor Chat
# -----------------------------

def ask_tutor(subject: str, level: str, user_question: str, history: List[dict] | None = None, language: str = "nl") -> str:
    """Stel een vraag aan een vakdocent-tutor. History is lijst van {role, content}."""
    if not _openai_available():
        return "AI-chat niet beschikbaar (geen API-key)."

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_msg = (
        "Je bent een behulpzame {}-docent op {} niveau. Antwoord zo helder mogelijk in {}."
    ).format(subject, level.upper(), language)

    messages = [
        {"role": "system", "content": system_msg},
    ]
    if history:
        # Voeg vorige berichten toe aan context
        messages.extend(history)
    # Voeg huidige vraag toe
    messages.append({"role": "user", "content": user_question})

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(Fout bij tutorchat: {e})"
