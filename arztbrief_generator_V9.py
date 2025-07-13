import streamlit as st
import base64
import tempfile
import os
from openai import OpenAI
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# Streamlit-Konfiguration
st.set_page_config(page_title="📄 Arztbrief aus Audio-Datei", layout="centered")
st.title("📄 Arztbrief aus Audio-Datei")

st.markdown("""
📁 Lade eine Arzt-Patienten-Aufnahme hoch (MP3, WAV, M4A, WEBM).  
Ein strukturierter Arztbrief wird automatisch generiert.
""")

# 🔐 API-Key Eingabe
st.markdown("""
🔐 Gib deinen persönlichen [OpenAI API-Key](https://platform.openai.com/account/api-keys) ein.  
Dein Key wird **nicht gespeichert** – er wird nur für diese Sitzung genutzt.
""")

api_key = st.text_input("OpenAI API-Key:", type="password")
if not api_key:
    st.info("Bitte gib deinen OpenAI API-Key ein, um fortzufahren.")
    st.stop()

# OpenAI Setup
client = OpenAI(api_key=api_key)

# PDF-Erstellung
def create_pdf_report(brief_text):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    elements = []
    for section in brief_text.split("\n\n"):
        lines = section.strip().split("\n", 1)
        if len(lines) == 2:
            heading, content = lines
            elements.append(Paragraph(f"<b>{heading}:</b>", styles["Heading4"]))
            elements.append(Paragraph(content.strip().replace("\n", "<br/>"), styles["BodyText"]))
            elements.append(Spacer(1, 12))
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Initialisierung
if "transcription_done" not in st.session_state:
    st.session_state.transcription_done = False

# Datei-Upload
uploaded_file = st.file_uploader("📤 Lade eine Audiodatei hoch", type=["mp3", "wav", "m4a", "webm"])

if uploaded_file:
    st.success("📥 Datei erfolgreich hochgeladen.")
    st.session_state.transcription_done = False

    with st.spinner("🔍 Transkription läuft..."):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="de"
                )
        except Exception:
            import subprocess
            import uuid
            st.warning("⚠️ Die Datei konnte nicht direkt verarbeitet werden. Versuche WAV-Konvertierung...")
            wav_path = tmp_path.replace(".webm", f"_{uuid.uuid4().hex}.wav")
            subprocess.run(["ffmpeg", "-y", "-i", tmp_path, wav_path], check=True)
            with open(wav_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="de"
                )
            os.remove(wav_path)

        os.remove(tmp_path)
        st.session_state.transcription_text = transcript.text
        st.session_state.transcription_done = True
        st.audio(uploaded_file, format="audio/webm")
        st.write("📝 Transkriptionstext (Ausschnitt):", transcript.text[:300])
        st.download_button("⬇️ Vollständige Transkription", transcript.text, file_name="transkript.txt")

# Strukturwahl und Arztbrief-Generierung
if st.session_state.transcription_done:
    st.markdown("## 🧾 Arztbriefstruktur wählen")

    struktur_optionen = {
        "Arztbrief Standard": """
Du bist ein medizinischer Assistent, der aus Transkripten strukturierte Arztbriefe erstellt.
Gliedere in: Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.
Füge drei passende ICD-10-Codes unter Diagnose hinzu (Format: Bezeichnung → Code).
""",
        "Kurzarztbrief": """
Erstelle einen kompakten medizinischen Arztbrief basierend auf einem Transkript.
Fasse die wichtigsten Punkte kurz und prägnant zusammen: Anamnese, Diagnose, Therapie.
Der Brief soll sich auf maximal eine halbe Seite beschränken.
""",
        "Ambulante Konsultation": """
Erstelle einen strukturierten Bericht einer ambulanten Konsultation.
Berücksichtige: Anlass, subjektiver Bericht, objektive Befunde, Diagnose(n), Therapieempfehlung.
""",
        "Stationäre Konsultation": """
Verfasse einen strukturierten Arztbrief einer stationären Konsultation.
Struktur: Aufnahmegrund, Anamnese, Untersuchungsbefunde, Verlauf, Entlassungsdiagnose(n), Empfehlung.
""",
        "Aufklärungsgespräch": """
Strukturiere den Text als Protokoll eines ärztlichen Aufklärungsgesprächs.
Gliedere in: Gesprächsinhalt, Risiken/Nebenwirkungen, Patientenfragen, Zustimmung des Patienten.
""",
        "Abschlussgespräch": """
Erstelle eine Zusammenfassung eines Abschlussgesprächs zwischen Arzt und Patient.
Strukturiere in: Behandlungsverlauf, aktueller Zustand, empfohlene Nachsorge, Patientenzufriedenheit.
""",
        "Angehörigengespräch": """
Protokolliere ein ärztliches Gespräch mit Angehörigen.
Gliedere in: Informationsstand der Angehörigen, besprochene Inhalte, Fragen und Sorgen, weiteres Vorgehen.
"""
    }

    ausgewählte_struktur = st.selectbox("📄 Strukturtyp für den Arztbrief", list(struktur_optionen.keys()))
    system_prompt = struktur_optionen[ausgewählte_struktur]

    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT erstellt den Arztbrief..."):
            chat = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": st.session_state.transcription_text}
                ],
                temperature=0.3
            )
            report = chat.choices[0].message.content.strip()

            st.subheader("📄 Generierter Arztbrief")
            st.text_area("Arztbrief mit ICD-10-Codes", report, height=400)

            pdf_buffer = create_pdf_report(report)
            st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
            st.download_button("⬇️ Arztbrief als Textdatei", report, file_name="arztbrief.txt")
