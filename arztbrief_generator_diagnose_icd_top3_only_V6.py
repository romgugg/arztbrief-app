import streamlit as st
import base64
import tempfile
import os
from openai import OpenAI
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
import streamlit.components.v1 as components

# OpenAI setup
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="🎤 Arztbrief aus Browser-Aufnahme", layout="centered")
st.title("🎤 Arztbrief aus Browser-Aufnahme")

st.markdown("""
🎙️ Nimm ein Arzt-Patienten-Gespräch direkt im Browser auf.
Ein strukturierter Arztbrief wird automatisch erstellt.
""")

# JavaScript Recorder Component with base64 return
audio_recorder_component = components.declare_component(
    name="audio_recorder",
    url="https://audiorecorder.streamlit.app"
)

# Use component
base64_audio = audio_recorder_component()

if base64_audio:
    st.success("✅ Aufnahme abgeschlossen und empfangen.")
    audio_bytes = base64.b64decode(base64_audio.split(",")[1])
    st.audio(audio_bytes, format="audio/webm")

    # Transcription
    with st.spinner("🧠 Transkription läuft..."):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
            f.write(audio_bytes)
            f.flush()
            with open(f.name, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="de"
                )
        os.remove(f.name)
        st.subheader("📝 Transkript")
        st.text_area("Transkribierter Text", transcript.text, height=250)

    # Arztbrief
    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT erstellt den Arztbrief..."):
            system_prompt = """
            Du bist ein medizinischer Assistent, der aus Transkripten strukturierte Arztbriefe erstellt.
            Gliedere in: Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.
            Füge drei passende ICD-10-Codes unter Diagnose hinzu (Format: Bezeichnung → Code).
            """
            chat = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript.text}
                ],
                temperature=0.3
            )
            report = chat.choices[0].message.content.strip()

        st.subheader("📄 Arztbrief")
        st.text_area("Arztbrief mit ICD-10-Codes", report, height=400)

        # PDF Export
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

        pdf_buffer = create_pdf_report(report)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", report, file_name="arztbrief.txt")
