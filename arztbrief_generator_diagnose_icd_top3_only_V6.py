import streamlit as st
import streamlit.components.v1 as components
import base64
import tempfile
import os
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from io import BytesIO

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="🎤 Arztbrief aus Audio", layout="centered")
st.title("🎤 Arztbrief aus Browser-Aufnahme")
st.markdown("🎙️ Nimm ein Arzt-Patienten-Gespräch direkt im Browser auf und generiere automatisch einen strukturierten Arztbrief.")

# === Aufnahme-Steuerung mit Statusanzeige ===
components.html("""
<script>
let mediaRecorder;
let audioChunks = [];

function startRecording() {
    document.getElementById("recordingStatus").innerText = "🔴 Aufnahme läuft...";
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };
            mediaRecorder.onstop = () => {
                document.getElementById("recordingStatus").innerText = "✅ Aufnahme abgeschlossen.";
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onloadend = () => {
                    const base64data = reader.result.split(',')[1];
                    const msg = {"isStreamlitMessage":true,"type":"streamlit:setComponentValue","value":base64data};
                    window.parent.postMessage(msg, "*");
                };
            };
            mediaRecorder.start();
        });
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
    }
}
</script>

<div>
  <button onclick="startRecording()">🎙️ Aufnahme starten</button>
  <button onclick="stopRecording()">⏹️ Aufnahme stoppen</button>
  <p id="recordingStatus" style="font-weight:bold; color:darkred; font-size:16px;"></p>
</div>
""", height=180)

# === Audiodaten empfangen ===
audio_base64 = st.query_params.get("value")

def transcribe_webm_bytes(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(audio_bytes)
        f.flush()
        with open(f.name, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="de"
            )
    return transcript.text

def generate_report_with_gpt(transkript):
    SYSTEM_PROMPT = """Du bist ein medizinischer Assistent, der aus Transkripten von Arzt-Patienten-Gesprächen strukturierte Arztbriefe erstellt.
Gliedere den Brief in folgende Abschnitte:

Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.

Formuliere die Diagnosen möglichst ICD-10-nah. Verwende eine sachliche, medizinisch korrekte Ausdrucksweise."""
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
        if capture and line.strip() == "":
            break
        if capture:
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

# === Nach der Aufnahme ===
if audio_base64:
    st.success("🎧 Aufnahme erfolgreich übertragen.")
    audio_bytes = base64.b64decode(audio_base64[0])
    st.audio(audio_bytes, format="audio/webm")

    with st.spinner("🧠 Transkription läuft…"):
        transkript = transcribe_webm_bytes(audio_bytes)
        st.subheader("📝 Transkript")
        st.text_area("Transkribierter Text", transkript, height=250)

    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT analysiert das Gespräch…"):
            report = generate_report_with_gpt(transkript)
            diagnose_text = extract_diagnose_section(report)
            gpt_icds = generate_icd_codes_with_gpt(diagnose_text)
            final_report = insert_gpt_icds_into_diagnosis(report, gpt_icds)

        st.subheader("📄 Arztbrief mit GPT-ICDs")
        st.text_area("Strukturierter Arztbrief", final_report, height=400)

        st.subheader("📎 GPT-generierte ICD-10-Codes")
        st.text(gpt_icds)

        st.subheader("📄 PDF-Export")
        logo_path = "logo.png"  # optional
        pdf_buffer = create_pdf_report(final_report, logo_path=logo_path)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", final_report, file_name="arztbrief.txt")
