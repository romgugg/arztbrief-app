
import streamlit as st
import whisper
from openai import OpenAI
import tempfile
import os
import re
import pandas as pd
from difflib import get_close_matches
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from io import BytesIO

# OpenAI Client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# === SYSTEMPROMPT ===
SYSTEM_PROMPT = """Du bist ein medizinischer Assistent, der aus Transkripten von Arzt-Patienten-Gesprächen strukturierte Arztbriefe erstellt.
Gliedere den Brief in folgende Abschnitte:

Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.

Verwende eine sachliche, medizinisch korrekte Ausdrucksweise. Vermute keine Inhalte, die nicht im Text vorkommen."""

@st.cache_resource
def load_model():
    return whisper.load_model("base")

@st.cache_resource
def load_icd10_mapping(filepath="icd10gm2025_codes.txt"):
    df = pd.read_csv(filepath, sep="|", header=None, dtype=str)
    df.columns = ["Stufe", "ID", "Ebene", "Code", "Leer1", "Leer2", "Leer3", "Beschreibung"]
    df = df[["Code", "Beschreibung"]].dropna()
    icd_map = {row["Beschreibung"].lower(): row["Code"] for _, row in df.iterrows()}
    return icd_map

def transcribe_audio(file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name
    model = load_model()
    result = model.transcribe(tmp_path, language="de")
    os.remove(tmp_path)
    return result["text"]

def generate_report_with_gpt(transcript):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Hier ist das Gespräch:\n{transcript}"}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3
    )
    return response.choices[0].message.content

def find_icd_codes_in_text(text, icd_map, threshold=0.85):
    found = set()
    words = set(text.lower().split())
    for desc in icd_map:
        tokens = set(desc.split())
        if tokens & words:
            found.add((desc.title(), icd_map[desc]))
        else:
            match = get_close_matches(desc, text.lower().split(), n=1, cutoff=threshold)
            if match:
                found.add((desc.title(), icd_map[desc]))
    return list(found)

def insert_multiple_icds_into_diagnosis(report_text, icd_map):
    lines = report_text.splitlines()
    new_lines = []
    inside_diagnose = False
    inserted = False
    all_icds = find_icd_codes_in_text(report_text, icd_map)

    for line in lines:
        new_lines.append(line)
        if line.strip().lower().startswith("diagnose"):
            inside_diagnose = True
        elif inside_diagnose and line.strip() == "":
            inside_diagnose = False
            if not inserted and all_icds:
                new_lines.append("ICD-10-Codes:")
                for term, code in all_icds:
                    new_lines.append(f"- {term} → {code}")
                inserted = True
    return "\n".join(new_lines)

def check_report_quality(report_text):
    checks = []
    if "Diagnose" not in report_text or "nicht dokumentiert" in report_text.split("Diagnose")[1][:100]:
        checks.append("⚠️ Diagnose fehlt oder unklar.")
    if "Therapie" not in report_text or "nicht dokumentiert" in report_text.split("Therapie")[1][:100]:
        checks.append("⚠️ Therapieempfehlung nicht angegeben.")
    if "Aufklärung" not in report_text:
        checks.append("⚠️ Keine Aufklärung dokumentiert.")
    if "Operationsplanung" not in report_text:
        checks.append("ℹ️ Kein OP-Termin genannt.")
    if "Zuweisung" not in report_text and "Blutbild" not in report_text:
        checks.append("ℹ️ Keine organisatorischen Hinweise (z. B. Blutbild, Zuweisung).")
    if not checks:
        checks.append("✅ Bericht scheint vollständig und strukturiert zu sein.")
    return checks

def create_pdf_report(brief_text, logo_path=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    elements = []

    if logo_path:
        try:
            img = Image(logo_path, width=150, height=50)
            elements.append(img)
            elements.append(Spacer(1, 20))
        except:
            pass

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

# === GPT-basierte ICD-Erkennung ===
def extract_icds_via_gpt(text, max_codes=3):
    system_prompt = (
        "Du bist ein medizinischer Kodierer. "
        "Analysiere den folgenden klinischen Text und extrahiere die relevantesten ICD-10-GM-Codes. "
        f"Gib maximal {max_codes} ICD-10-Codes mit zugehöriger Diagnosebezeichnung zurück. "
        "Nutze das Format: <Code>: <Bezeichnung>, einer pro Zeile."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0
    )

    return response.choices[0].message.content

# === Streamlit UI ===
st.set_page_config(page_title="Arztbrief aus Audio", layout="centered")
st.title("🎤 Arztbrief aus Audioaufnahme")

st.markdown("Lade ein Arzt-Patienten-Gespräch hoch (mp3/wav/m4a). Der strukturierte Arztbrief wird automatisch erstellt.")

with st.spinner("📚 Lade ICD-10-Daten…"):
    icd_map = load_icd10_mapping()

audio_file = st.file_uploader("📁 Audioaufnahme hochladen", type=["mp3", "wav", "m4a"])

if audio_file:
    with st.spinner("🔍 Transkription läuft…"):
        transkript = transcribe_audio(audio_file)
    st.success("✅ Transkription abgeschlossen.")
    st.subheader("📝 Transkript")
    st.text_area("Transkribierter Text", transkript, height=250)

    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT analysiert das Gespräch…"):
            report = generate_report_with_gpt(transkript)
            report_with_icd = insert_multiple_icds_into_diagnosis(report, icd_map)

        st.subheader("📄 Generierter Arztbrief")
        st.text_area("Arztbrief mit ICD-10", report_with_icd, height=400)

        st.subheader("🧪 Regelprüfung")
        feedback = check_report_quality(report_with_icd)
        for msg in feedback:
            if "⚠️" in msg:
                st.error(msg)
            elif "ℹ️" in msg:
                st.info(msg)
            else:
                st.success(msg)

        st.subheader("📘 Gefundene ICD-10-Codes (Wortbasiert)")
        codes = find_icd_codes_in_text(report_with_icd, icd_map)
        for term, code in codes:
            st.markdown(f"- **{term}** → `{code}`")

        st.subheader("🧠 GPT-gestützte ICD-10-Vorschläge")
        gpt_icds = extract_icds_via_gpt(report_with_icd)
        st.text_area("📋 GPT-Vorschläge", gpt_icds, height=150)

        st.subheader("📄 PDF-Export")
        logo_path = "logo.png"
        pdf_buffer = create_pdf_report(report_with_icd, logo_path=logo_path)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", report_with_icd, file_name="arztbrief.txt")
