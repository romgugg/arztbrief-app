import streamlit as st
import base64
import tempfile
import os
from openai import OpenAI
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

# OpenAI setup
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="🎤 Arztbrief aus Browser-Aufnahme", layout="centered")
st.title("🎤 Arztbrief aus Browser-Aufnahme")

st.markdown("""
🎙️ Nimm ein Arzt-Patienten-Gespräch direkt im Browser auf.
Ein strukturierter Arztbrief wird automatisch erstellt.
""")

# HTML/JS Recorder
components.html("""
<script>
let mediaRecorder;
let audioChunks = [];
function startRecording() {
    document.getElementById("status").innerText = "🔴 Aufnahme läuft...";
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };
            mediaRecorder.onstop = () => {
                document.getElementById("status").innerText = "✅ Aufnahme abgeschlossen.";
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onloadend = () => {
                    const base64data = reader.result;
                    window.parent.postMessage({ type: 'FROM_IFRAME', base64: base64data }, '*');
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
    <p id="status" style="font-weight:bold; color:darkred;"></p>
</div>
""", height=200)

# Listen to message from iframe
js_code = """
await new Promise(resolve => {
  window.addEventListener('message', (event) => {
    if (event.data && event.data.base64) {
      resolve(event.data.base64);
    }
  }, { once: true });
})
"""

if "audio_base64" not in st.session_state:
    st.session_state.audio_base64 = None
if "transcription_done" not in st.session_state:
    st.session_state.transcription_done = False

js_response = streamlit_js_eval(js_expressions=js_code, key="recorder", trigger=True)
if js_response and not st.session_state.audio_base64:
    st.success("📥 Audio wurde empfangen und gespeichert.")
    st.session_state.audio_base64 = js_response
    st.session_state.transcription_done = False
    audio_bytes = base64.b64decode(js_response.split(",")[1])
    st.audio(audio_bytes, format="audio/webm")
    with st.expander("🔍 Debug: Audio-Base64 anzeigen"):
        st.code(js_response[:100] + "...", language="text")
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
    st.session_state.transcription_text = transcript.text
    st.session_state.transcription_done = True
    st.write("📝 Transkriptionstext (Ausschnitt):", st.session_state.transcription_text[:300])
    st.write("📝 Transkriptionstext (Ausschnitt):", st.session_state.transcription_text[:300])

audio_ready = st.session_state.audio_base64 is not None
transcribe_disabled = not audio_ready

st.divider()

# Optionale manuelle Datei-Upload-Funktion
uploaded_file = st.file_uploader("📁 Oder lade eine Audiodatei hoch (MP3, WAV, M4A, WEBM)", type=["mp3", "wav", "m4a", "webm"])

if uploaded_file:
    st.success("📥 Datei erfolgreich hochgeladen.")
    st.session_state.transcription_done = False
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(uploaded_file.read())
        f.flush()
        with open(f.name, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="de"
            )
    os.remove(f.name)
    st.session_state.audio_base64 = None
    st.session_state.transcription_text = transcript.text
    st.session_state.transcription_done = True
    st.audio(uploaded_file, format="audio/webm")
    st.write("📝 Transkriptionstext (Ausschnitt):", transcript.text[:300])

    if st.button("🧠 Arztbrief generieren mit GPT"):
    # GPT-Analyse und Arztbrief
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

        def create_pdf_report(brief_text):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    elements = []
    for section in brief_text.split("

"):
        lines = section.strip().split("
", 1)
        if len(lines) == 2:
            heading, content = lines
            elements.append(Paragraph(f"<b>{heading}:</b>", styles["Heading4"]))
            elements.append(Paragraph(content.strip().replace("
", "<br/>"), styles["BodyText"]))
            elements.append(Spacer(1, 12))
    doc.build(elements)
    buffer.seek(0)
    return buffer

        pdf_buffer = create_pdf_report(report)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")
        st.download_button("⬇️ Arztbrief als Textdatei", report, file_name="arztbrief.txt")
