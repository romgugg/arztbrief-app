import streamlit as st
import openai
import tempfile
import os
import subprocess
import pandas as pd
from difflib import get_close_matches
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from io import BytesIO

# OpenAI-Client (API-Key aus Streamlit Secrets)
from openai import OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """Du bist ein medizinischer Assistent, der aus Transkripten von Arzt-Patienten-Gesprächen strukturierte Arztbriefe erstellt.
Gliedere den Brief in folgende Abschnitte:

Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.

Verwende eine sachliche, medizinisch korrekte Ausdrucksweise. Vermute keine Inhalte, die nicht im Text vorkommen."""

@st.cache_resource
def load_icd10_mapping(filepath="icd10gm2025_codes.txt"):
    df = pd.read_csv(filepath, sep="|", header=None, dtype=str)
    df.columns = ["Stufe", "ID", "Ebene", "Code", "Leer1", "Leer2", "Leer3", "Beschreibung"]
    df = df[["Code", "Beschreibung"]].dropna()
    icd_map = {row["Beschreibung"].lower(): row["Code"] for _, row in df.iterrows()}
    return icd_map

# ✅ ffmpeg-basierte Audioverarbeitung (robust für m4a/mp3/wav)
def transcribe_audio(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as in_file:
        in_file.write(uploaded_file.read())
        in_path = in_file.name

    out_path = in_path.replace(suffix, ".wav")

    try:
        subprocess.run(
            ["ffmpeg", "-i", in_path, "-ar", "16000", "-ac", "1", "-f", "wav", out_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        with open(out_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="de"
            )
        return transcript.text

    except Exception as e:
        raise RuntimeError(f"❌ Fehler bei Audio-Konvertierung oder Transkription: {e}")

    finally:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)

def generate_report_with_gpt(transkript):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Hier ist das Gespräch:
{transkript}"""}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3
    )
    return response.choices[0].message.content

def find_icd_codes_in_diagnose_section(report_text, icd_map, top_n=3, threshold=0.85):
    diagnosis = ""
    capture = False
    for line in report_text.splitlines():
        if line.strip().lower().startswith("diagnose"):
            capture = True
            continue
        if capture:
            if line.strip() == "":
                break
            diagnosis += line + " "
    diagnosis_words = set(diagnosis.lower().split())
    matches = []
    for desc, code in icd_map.items():
        desc_words = set(desc.lower().split())
        if desc_words & diagnosis_words:
            matches.append((desc.title(), code))
        else:
            if get_close_matches(desc.lower(), diagnosis_words, n=1, cutoff=threshold):
                matches.append((desc.title(), code))
    return matches[:top_n]

def insert_icds_into_diagnosis(report_text, icd_map):
    lines = report_text.splitlines()
    new_lines = []
    inside_diagnose = False
    inserted = False
    top_icds = find_icd_codes_in_diagnose_section(report_text, icd_map)

    for line in lines:
        new_lines.append(line)
        if line.strip().lower().startswith("diagnose"):
            inside_diagnose = True
        elif inside_diagnose and line.strip() == "":
            inside_diagnose = False
            if not inserted and top_icds:
                new_lines.append("ICD-10-Codes:")
                for term, code in top_icds:
                    new_lines.append(f"- {term} → {code}")
                inserted = True
    return "\n".join(new_lines)

def create_pdf_report(brief_text, logo_path=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    elements = []

    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=150, height=50)
            elements.append(img)
            elements.append(Spacer(1, 20))
        except Exception as e:
            print(f"⚠️ Logo konnte nicht geladen werden: {e}")

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

# === Streamlit UI ===
st.set_page_config(page_title="Arztbrief aus Audio", layout="centered")
st.title("🎤 Arztbrief aus Audioaufnahme")

st.markdown("Lade ein Arzt-Patienten-Gespräch hoch (mp3/wav/m4a). Der strukturierte Arztbrief wird automatisch erstellt.")

with st.spinner("📚 Lade ICD-10-Daten…"):
    icd_map = load_icd10_mapping()

audio_file = st.file_uploader("📁 Audioaufnahme hochladen", type=["mp3", "wav", "m4a"])

if audio_file:
    with st.spinner("🔍 Transkription läuft…"):
        try:
            transkript = transcribe_audio(audio_file)
            st.success("✅ Transkription abgeschlossen.")
            st.subheader("📝 Transkript")
            st.text_area("Transkribierter Text", transkript, height=250)
        except Exception as e:
            st.error(str(e))
            st.stop()

    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT analysiert das Gespräch…"):
            report = generate_report_with_gpt(transkript)
            report_with_icd = insert_icds_into_diagnosis(report, icd_map)

        st.subheader("📄 Generierter Arztbrief")
        st.text_area("Arztbrief mit ICD-10", report_with_icd, height=400)

        st.subheader("📄 PDF-Export")
        logo_path = "logo.png"
        pdf_buffer = create_pdf_report(report_with_icd, logo_path=logo_path)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", report_with_icd, file_name="arztbrief.txt")
