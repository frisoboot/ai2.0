# 🎓 AI Examen Trainer

Een simpele maar moderne oefenomgeving voor eindexamens (Nederlands, Engels, Geschiedenis) met AI-feedback en gepersonaliseerde vervolgvragen.

## Features

1. Streamlit-interface: werkt lokaal of op eender welk server-platform.
2. SQLite-database: bewaart vragen en resultaten.
3. GPT-ondersteuning (optioneel): geeft uitleg bij fouten en stelt nieuwe vragen voor.

## Installatie

```bash
# Repo/clonen is niet nodig – dit project staat al op je machine:
cd /pad/naar/ai_exam_trainer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Voeg je OpenAI-API-sleutel toe (optioneel):

```bash
echo "export OPENAI_API_KEY='sk-...'" >> ~/.zshrc && source ~/.zshrc
```

## Starten

```bash
streamlit run main.py
```

De app opent automatisch in je browser. Kies een vak, maak het examen en bekijk de AI-feedback.

## Eigen vragen toevoegen

• Open `db.py` en breid de `seed_sample_questions`-lijst uit, of stop volledig eigen examenvragen in de SQLite-tabel `questions` met bijvoorbeeld DB-Browser.

## Roadmap (suggesties)

- Inlogfunctionaliteit voor leerlingen.
- Analyse-dashboard per leerling en vak.
- Upload van PDF-examens om automatisch vragen te genereren. 