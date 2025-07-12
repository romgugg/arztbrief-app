
import streamlit as st
import openai
import tempfile
import os
import pandas as pd
from difflib import get_close_matches
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from io import BytesIO

# OpenAI API-Key setzen
openai.api_key = st.secrets["OPENAI_API_KEY"]

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

def transcribe_audio(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=f,
            language="de"
        )

    os.remove(tmp_path)
    return transcript["text"]
