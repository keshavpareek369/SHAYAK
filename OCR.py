import streamlit as st
import pytesseract
from PIL import Image
import re

# Optional: specify path to Tesseract (for Windows)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

st.set_page_config(page_title="Smart Document Identifier", layout="centered")
st.title("📄 Smart Document Type Identifier using OCR")

st.write("Upload a document image (Aadhaar, PAN, or Driving License) — "
         "the app will detect which one it is based on OCR text patterns.")

uploaded_file = st.file_uploader("Upload Document Image", type=["jpg", "jpeg", "png"])

def detect_document_type(text):
    text = text.upper()

    # Aadhaar detection (12-digit + UIDAI or DOB + MALE/FEMALE)
    if re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", text) or "AADHAAR" in text or "UNIQUE IDENTIFICATION" in text:
        return "🪪 Aadhaar Card"

    # PAN detection (10-character alphanumeric pattern)
    elif re.search(r"[A-Z]{5}[0-9]{4}[A-Z]{1}", text) or "INCOME TAX" in text or "PERMANENT ACCOUNT NUMBER" in text:
        return "🧾 PAN Card"

    # Driving License detection
    elif re.search(r"\bDL[-\s]*\d+", text) or "DRIVING LICENCE" in text or "TRANSPORT" in text:
        return "🚗 Driving License"

    else:
        return "❓ Unknown Document Type"

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Document", use_column_width=True)

    with st.spinner("Extracting text using OCR..."):
        extracted_text = pytesseract.image_to_string(image)

    st.subheader("🧾 Extracted Text:")
    st.text_area("Extracted Text", extracted_text, height=200)

    doc_type = detect_document_type(extracted_text)
    st.subheader("📑 Detected Document Type:")
    st.success(doc_type)

    # Optional: extract some basic info if Aadhaar detected
    if "AADHAAR" in doc_type or "🪪" in doc_type:
        name_match = re.search(r"([A-Z][a-z]+\s[A-Z][a-z]+)", extracted_text)
        dob_match = re.search(r"\d{2}/\d{2}/\d{4}", extracted_text)
        aadhaar_match = re.search(r"\d{4}\s\d{4}\s\d{4}", extracted_text)

        st.subheader("🧍 Extracted Information:")
        if name_match:
            st.write(f"**Name:** {name_match.group(1)}")
        if dob_match:
            st.write(f"**Date of Birth:** {dob_match.group(0)}")
        if aadhaar_match:
            st.write(f"**Aadhaar Number:** {aadhaar_match.group(0)}")
