import streamlit as st
import openai
import tempfile
import os
import subprocess
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from io import BytesIO

# OpenAI-Client
from openai import OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """Du bist ein medizinischer Assistent, der aus Transkripten von Arzt-Patienten-Gesprächen strukturierte Arztbriefe erstellt.
Gliedere den Brief in folgende Abschnitte:

Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.

Formuliere die Diagnosen möglichst ICD-10-nah, z. B. 'Essentielle Hypertonie' statt 'Bluthochdruck'.
Verwende eine sachliche, medizinisch korrekte Ausdrucksweise. Vermute keine Inhalte, die nicht im Text vorkommen."""

# === Funktionen ===

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
        raise RuntimeError(f"Fehler bei Audioverarbeitung: {e}")

    finally:
        if os.path.exists(in_path): os.remove(in_path)
        if os.path.exists(out_path): os.remove(out_path)

def generate_report_with_gpt(transkript):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Hier ist das Gespräch:\n{transkript}"}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def extract_diagnose_section(report_text):
    diagnosis = ""
    capture = False
    for line in report_text.splitlines():
        if "diagnose" in line.strip().lower():
            capture = True
            continue
        if capture:
            if line.strip() == "":
                break
            diagnosis += line + " "
    return diagnosis.strip()

def generate_icd_codes_with_gpt(diagnose_text):
    prompt = f"""
Die folgende medizinische Diagnose lautet:

{diagnose_text}

Bitte gib die drei zutreffendsten ICD-10-GM-Codes an. Format: „Bezeichnung → Code“. Verwende offizielle deutsche ICD-Bezeichnungen.
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Du bist ein medizinischer Kodierexperte für ICD-10-GM."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

def insert_gpt_icds_into_diagnosis(report_text, gpt_icds_text):
    lines = report_text.splitlines()
    new_lines = []
    inside_diagnose = False
    inserted = False

    for line in lines:
        new_lines.append(line)
        if "diagnose" in line.strip().lower():
            inside_diagnose = True
        elif inside_diagnose and line.strip() == "":
            inside_diagnose = False
            if not inserted and gpt_icds_text:
                new_lines.append("GPT-generierte ICD-10-Codes:")
                for icd_line in gpt_icds_text.strip().splitlines():
                    new_lines.append(f"- {icd_line.strip()}")
                inserted = True

    if not inserted and gpt_icds_text:
        new_lines.append("\nGPT-generierte ICD-10-Codes:")
        for icd_line in gpt_icds_text.strip().splitlines():
            new_lines.append(f"- {icd_line.strip()}")

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

# === Streamlit UI ===

st.set_page_config(page_title="Arztbrief aus Audio", layout="centered")
st.title("🎤 Arztbrief aus Audioaufnahme")
st.markdown("Lade ein Arzt-Patienten-Gespräch hoch (mp3/wav/m4a). Der strukturierte Arztbrief wird automatisch erstellt.")

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
            diagnose_text = extract_diagnose_section(report)
            gpt_icds = generate_icd_codes_with_gpt(diagnose_text)
            final_report = insert_gpt_icds_into_diagnosis(report, gpt_icds)

        st.subheader("📄 Arztbrief (mit GPT-ICDs)")
        st.text_area("Strukturierter Arztbrief", final_report, height=400)

        st.subheader("🧠 GPT-generierte ICD-10-Codes")
        st.text(gpt_icds)

        st.subheader("📄 PDF-Export")
        logo_path = "logo.png"  # optional
        pdf_buffer = create_pdf_report(final_report, logo_path=logo_path)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", final_report, file_name="arztbrief.txt")
