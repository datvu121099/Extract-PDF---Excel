import re
import io
import pandas as pd
from datetime import datetime
import streamlit as st

# --- Page config ---
st.set_page_config(
    page_title="PDF → Excel Extractor",
    page_icon="📄",
    layout="centered"
)

st.title("📄 PDF → Excel Extractor")
st.markdown("Upload a PDF bill file to extract call detail data into an Excel file.")

# --- Helper: extract from raw text ---
def extract_from_text(content: str) -> list[dict]:
    date_pattern = r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})"
    total_row_pattern = r"\|\s*([\w\d]+)\s*\|\s*Tổng\s*\|\s*([\d\.,]+)\s*\|"

    current_formatted_date = "N/A"
    rows = []

    date_match = re.search(date_pattern, content)
    if date_match:
        full_date_str = date_match.group(1)
        try:
            date_obj = datetime.strptime(full_date_str, "%d/%m/%Y %H:%M:%S")
            current_formatted_date = date_obj.strftime("%m%Y")
        except ValueError:
            current_formatted_date = "N/A"

    for line in content.split("\n"):
        match = re.search(total_row_pattern, line)
        if match:
            rows.append({
                "Date": current_formatted_date,
                "So_TB": match.group(1).strip(),
                "Tong_Cuoc": match.group(2).strip(),
            })

    return rows

# --- Helper: read PDF text via llama_index ---
@st.cache_data(show_spinner=False)
def process_pdf(file_bytes: bytes, filename: str) -> pd.DataFrame:
    import tempfile, os
    from llama_index.core import SimpleDirectoryReader

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, filename)
        with open(pdf_path, "wb") as f:
            f.write(file_bytes)

        documents = SimpleDirectoryReader(tmpdir).load_data()

    all_rows = []
    for doc in documents:
        all_rows.extend(extract_from_text(doc.get_content()))

    return pd.DataFrame(all_rows)

# --- Helper: df → Excel bytes ---
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="KetQua")
    return buf.getvalue()

# --- UI ---
uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

if uploaded_file:
    st.info(f"File uploaded: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

    with st.spinner("Extracting data from PDF…"):
        try:
            df = process_pdf(uploaded_file.read(), uploaded_file.name)
        except Exception as e:
            st.error(f"Extraction failed: {e}")
            st.stop()

    if df.empty:
        st.warning("No matching rows found in this PDF. Make sure the file contains the expected table format.")
    else:
        st.success(f"Extracted **{len(df)} rows** successfully!")

        st.dataframe(df, use_container_width=True)

        # Build download filename
        file_date = df["Date"].iloc[0] if "Date" in df.columns else "unknown"
        excel_filename = f"ket_qua_cuoc_chi_tiet_{file_date}.xlsx"
        excel_bytes = to_excel_bytes(df)

        st.download_button(
            label="⬇️ Download Excel file",
            data=excel_bytes,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
