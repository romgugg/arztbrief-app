if "arztbrief" not in st.session_state:
    st.session_state.arztbrief = ""
if "arztbrief_generiert" not in st.session_state:
    st.session_state.arztbrief_generiert = False

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
        st.session_state.arztbrief = chat.choices[0].message.content.strip()
        st.session_state.arztbrief_generiert = True

if st.session_state.arztbrief_generiert:
    st.subheader("📄 Generierter Arztbrief")
    edited_report = st.text_area("✏️ Arztbrief bearbeiten (optional)", st.session_state.arztbrief, height=400)

    pdf_layout = st.selectbox("🖨️ PDF-Layout wählen", ["Standard (nur Text)", "Mit Logo & Briefkopf"], key="layout_select")
    briefkopf_aktiv = pdf_layout == "Mit Logo & Briefkopf"

    if st.button("📄 PDF jetzt generieren", key="generate_pdf"):
        pdf_buffer = create_pdf_report(edited_report, mit_briefkopf=briefkopf_aktiv)
        st.download_button("⬇️ PDF herunterladen", data=pdf_buffer, file_name="arztbrief.pdf", mime="application/pdf")

    st.download_button("⬇️ Arztbrief als Textdatei", edited_report, file_name="arztbrief.txt")
