import streamlit as st
import streamlit.components.v1 as components
import base64
import tempfile
import os
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from io import BytesIO

# OpenAI Client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="🎤 Arztbrief aus Audio", layout="centered")
st.title("🎤 Arztbrief aus Browser-Aufnahme")
st.markdown("🎙️ Nimm ein Arzt-Patienten-Gespräch direkt im Browser auf. Ein strukturierter Arztbrief wird automatisch erstellt.")

# === Aufnahme-Buttons und Statusanzeige ===
components.html("""
<script>
let mediaRecorder;
let audioChunks = [];

function startRecording() {
    document.getElementById("status").innerText = "🔴 Aufnahme läuft...";
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
        mediaRecorder.onstop = () => {
            document.getElementById("status").innerText = "✅ Aufnahme abgeschlossen.";
            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64data = reader.result.split(',')[1];
                const message = {
                    isStreamlitMessage: true,
                    type: "streamlit:setComponentValue",
                    value: base64data
                };
                window.parent.postMessage(message, "*");
            };
            reader.readAsDataURL(blob);
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
  <p id="status" style="font-weight:bold; color:darkred;"></p>
</div>
""", height=180)

# === Audiodaten empfangen ===
audio_base64 = st.query_params.get("value")

if audio_base64:
    audio_bytes = base64.b64decode(audio_base64[0])
    st.success("✅ Aufnahme erfolgreich empfangen.")
    st.audio(audio_bytes, format="audio/webm")

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

    if st.button("🧠 Arztbrief generieren mit GPT"):
        with st.spinner("💬 GPT analysiert das Gespräch…"):
            system_prompt = """Du bist ein medizinischer Assistent, der aus Transkripten strukturierte Arztbriefe erstellt.
Gliedere den Text in: Anamnese, Diagnose, Therapie, Aufklärung, Organisatorisches, Operationsplanung, Patientenwunsch.
Füge unter „Diagnose“ drei zutreffende ICD-10-Codes im Format: Bezeichnung → Code hinzu.
"""
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript.text}
                ],
                temperature=0.3
            )
            report = response.choices[0].message.content.strip()

        st.subheader("📄 Arztbrief mit ICD-10")
        st.text_area("Strukturierter Arztbrief", report, height=400)

        # PDF Export
        def create_pdf(text):
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50)
            styles = getSampleStyleSheet()
            elements = []
            for section in text.split("\n\n"):
                parts = section.strip().split("\n", 1)
                if len(parts) == 2:
                    title, content = parts
                    elements.append(Paragraph(f"<b>{title}</b>", styles["Heading4"]))
                    elements.append(Paragraph(content.replace("\n", "<br/>"), styles["BodyText"]))
                    elements.append(Spacer(1, 12))
            doc.build(elements)
            buffer.seek(0)
            return buffer

        pdf = create_pdf(report)
        st.download_button("⬇️ PDF herunterladen", data=pdf, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", report, file_name="arztbrief.txt")
