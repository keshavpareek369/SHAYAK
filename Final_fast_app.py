import os
import json
import re
import pytesseract
import streamlit as st
from PIL import Image
import speech_recognition as sr
from dotenv import load_dotenv
from datetime import datetime

# LangChain / LLM imports
from langchain.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

# =========================
# CONFIG
# =========================
load_dotenv()

# Set path to tesseract if needed (Windows). Change if different path or comment out.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

JSON_PATH = "schemes.json"
ELIGIBILITY_JSON_PATH = "eligibility_summary-2.json"
DB_DIR = "rag_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HISTORY_PATH = "user_history.json"

st.set_page_config(page_title="Intelligent Government Scheme Assistant (SAHAYAK)", layout="wide")

# =========================
# USER HISTORY SYSTEM
# =========================
def load_user_history():
    """Load user search history from JSON file"""
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading history: {e}")
        return []

def save_user_history(entry):
    """Save a new search entry to user history"""
    history = load_user_history()
    history.append(entry)
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error saving history: {e}")

def get_user_id(name, aadhaar):
    """Generate unique user ID from name and aadhaar"""
    if aadhaar and len(aadhaar) >= 4:
        return f"{name}_{aadhaar[-4:]}"
    return name.strip().replace(" ", "_")

# =========================
# Load RAG data with optimized loading
# =========================
@st.cache_resource
def load_data():
    """Load schemes data and create vector database with progress tracking"""
    
    # Check if vector DB already exists - much faster loading
    if os.path.exists(DB_DIR) and os.path.exists(os.path.join(DB_DIR, "chroma.sqlite3")):
        try:
            embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
            vectordb = Chroma(persist_directory=DB_DIR, embedding_function=embeddings)
            
            with open(ELIGIBILITY_JSON_PATH, "r", encoding="utf-8") as f:
                eligibility_json = json.load(f)
            eligibility_data = {item["scheme_name"]: item["eligibility"] for item in eligibility_json}
            
            # Get approximate doc count
            num_docs = len(eligibility_data)
            return vectordb, eligibility_data, num_docs, True
        except Exception as e:
            st.warning(f"Existing DB load failed: {e}. Rebuilding...")
    
    # Build new vector DB (slower first-time process)
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    for entry in data:
        kb = entry["knowledge_base_entry"]
        text_parts = [f"Scheme: {kb.get('scheme', '')}", f"Summary: {kb.get('summary', '')}"]

        for section in ["key_information", "all_extracted_sections"]:
            section_data = kb.get(section, {})
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    if isinstance(value, list):
                        text_parts.extend(value)
                    elif isinstance(value, str):
                        text_parts.append(value)

        full_text = "\n".join(text_parts).strip()
        if full_text:
            docs.append(Document(page_content=full_text, metadata={"scheme": kb.get("scheme", "Unknown")}))

    with open(ELIGIBILITY_JSON_PATH, "r", encoding="utf-8") as f:
        eligibility_json = json.load(f)

    eligibility_data = {item["scheme_name"]: item["eligibility"] for item in eligibility_json}

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectordb = Chroma.from_documents(chunks, embedding=embeddings, persist_directory=DB_DIR)
    vectordb.persist()

    return vectordb, eligibility_data, len(docs), False

# Initialize session state for loading status
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.vectordb = None
    st.session_state.eligibility_data = {}
    st.session_state.num_docs = 0

# =========================
# Sidebar: API keys (user input) + fallback
# =========================
st.sidebar.header("🔑 API Keys (optional)")
user_groq_key = st.sidebar.text_input("Groq API Key (leave empty to use fallback)", type="password")
user_gemini_key = st.sidebar.text_input("Gemini API Key (leave empty to use fallback)", type="password")

# FALLBACK (hardcoded) keys – used only if user doesn't provide their own
GROQ_FALLBACK = None  # set to a string if you have a fallback Groq key
GEMINI_FALLBACK = None  # set to a string if you have a fallback Gemini key

def get_llm_instance(llm_choice):
    """
    Uses user-provided key if present, otherwise falls back to hardcoded.
    """
    groq_key = user_groq_key.strip() or GROQ_FALLBACK
    gemini_key = user_gemini_key.strip() or GEMINI_FALLBACK

    if llm_choice.lower() == "grok":
        try:
            return ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=groq_key)
        except Exception as e:
            st.error(f"Failed to initialize Groq: {e}")
            return None
    elif llm_choice.lower() == "gemini":
        try:
            if gemini_key:
                return ChatGoogleGenerativeAI(model="gemini-2.0-flash-001", temperature=0, google_api_key=gemini_key)
            else:
                return ChatGoogleGenerativeAI(model="gemini-2.0-flash-001", temperature=0)
        except Exception as e:
            st.error(f"Failed to initialize Gemini: {e}")
            return None
    return None

# =========================
# Utility: retrieval context
# =========================
def retrieve_context(query, k=10):
    """Retrieve relevant context from vector database"""
    if vectordb is None:
        return ""
    retriever = vectordb.as_retriever(search_kwargs={"k": k})
    results = retriever.get_relevant_documents(query)
    return "\n\n".join([r.page_content for r in results])

def get_top_schemes_from_query(query, top_k=30, search_k=500):
    """Get top relevant schemes based on query"""
    if vectordb is None:
        return []
    retriever = vectordb.as_retriever(search_kwargs={"k": search_k})
    results = retriever.get_relevant_documents(query)
    seen, top_schemes = set(), []
    for doc in results:
        name = doc.metadata.get("scheme")
        if name and name not in seen:
            top_schemes.append(name)
            seen.add(name)
        if len(top_schemes) >= top_k:
            break
    return top_schemes

def filter_eligible_schemes(client_profile, schemes, eligibility_data, llm_choice="gemini"):
    """Filter schemes based on eligibility criteria using LLM reasoning"""
    filtered, reasoning_results = [], {}
    llm = get_llm_instance(llm_choice)
    if llm is None:
        st.error("LLM initialization failed – check your API key or LLM selection.")
        return filtered, reasoning_results

    profile_text = (
        f"{client_profile.get('name', 'User')} is a {client_profile.get('age', '')}-year-old "
        f"{client_profile.get('gender', '')} {client_profile.get('nationality', '')} citizen. "
        f"They belong to the {client_profile.get('caste', 'General')} category. "
        f"They are working as a {client_profile.get('occupation', '')} "
        f"and pursuing {client_profile.get('education', '')}. "
        f"Their annual income is {client_profile.get('income', 0)} rupees. "
        f"Aadhaar linked: {client_profile.get('aadhaar_linked', False)}."
    ).strip()

    for scheme in schemes:
        criteria = eligibility_data.get(scheme)
        if not criteria:
            continue
        eligibility_text = ". ".join([f"{k}: {v}" for k, v in criteria.items()])

        prompt = f"""
        You are an intelligent government scheme eligibility evaluator.
        Evaluate whether this person is eligible for the scheme based on reasoning.
        Base your judgment strictly on the scheme's eligibility criteria – don't assume missing data.
        Consider caste, age, income, gender, occupation, and education.
        Respond with a short logical explanation and end with "Eligible: Yes" or "Eligible: No".

        Person Profile:
        {profile_text}

        Scheme Eligibility Requirements:
        {eligibility_text}

        Answer:
        """

        try:
            response = llm.invoke(prompt)
            reasoning_text = response.content.strip()
        except Exception as e:
            reasoning_text = f"Error during reasoning: {e}"

        reasoning_results[scheme] = {"reasoning": reasoning_text}
        if "eligible: yes" in reasoning_text.lower():
            filtered.append(scheme)

    return filtered, reasoning_results

# =========================
# OCR + Aadhaar auto-fill helpers
# =========================
def detect_document_type(text):
    """Detect document type from OCR text"""
    t = text.upper()
    if re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", t) or "AADHAAR" in t or "UNIQUE IDENTIFICATION" in t:
        return "Aadhaar"
    if re.search(r"[A-Z]{5}[0-9]{4}[A-Z]{1}", t) or "INCOME TAX" in t or "PERMANENT ACCOUNT NUMBER" in t:
        return "PAN"
    if re.search(r"\bDL[-\s]*\d+", t) or "DRIVING LICENCE" in t or "TRANSPORT" in t:
        return "Driving License"
    return "Unknown"

def extract_aadhaar_details(text):
    """Extract personal details from Aadhaar card text"""
    details = {"name": None, "dob": None, "gender": None, "aadhaar_number": None}
    # Aadhaar number pattern
    match = re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", text)
    if match:
        details["aadhaar_number"] = match.group(0).replace(" ", "")
    # DOB patterns (dd/mm/yyyy or dd-mm-yyyy)
    dob = re.search(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", text)
    if dob:
        details["dob"] = dob.group(0)
    # Gender
    if "MALE" in text.upper():
        details["gender"] = "male"
    elif "FEMALE" in text.upper():
        details["gender"] = "female"
    # Name (heuristic: two capitalized words)
    name = re.search(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)+", text)
    if name:
        details["name"] = name.group(0)
    return details

# =========================
# SIDEBAR: USER HISTORY
# =========================
st.sidebar.markdown("---")
st.sidebar.markdown("## 📜 Your Search History")

if st.sidebar.button("🔍 View My History"):
    all_history = load_user_history()
    # Get current user info from session state if available
    current_name = st.session_state.get("current_user_name", "")
    current_aadhaar = st.session_state.get("current_user_aadhaar", "")
    
    if current_name:
        user_id = get_user_id(current_name, current_aadhaar)
        my_history = [h for h in all_history if h.get("user_id") == user_id]
        
        if not my_history:
            st.sidebar.info("No history found for this user.")
        else:
            st.sidebar.success(f"Found {len(my_history)} searches")
            for item in reversed(my_history[-5:]):  # Show last 5 searches
                st.sidebar.markdown(f"""
                🕒 **{item.get('timestamp', 'N/A')}**  
                📝 Query: {item.get('query', 'N/A')[:50]}...  
                ✅ {len(item.get('eligible_schemes', []))} schemes found
                ---
                """)
    else:
        st.sidebar.warning("Please enter your name to view history")

# Admin view - full history
with st.sidebar.expander("📊 View All History (Admin)"):
    hist = load_user_history()
    if hist:
        st.dataframe(hist)
    else:
        st.info("No history stored yet.")

# =========================
# STREAMLIT UI: main page
# =========================
st.title("🛡️ Intelligent Government Scheme Assistant (SAHAYAK)")
st.write("Find which government schemes you're eligible for – using RAG + LLM reasoning.")

# Load data asynchronously with UI feedback
if not st.session_state.data_loaded:
    with st.spinner("🔄 Loading scheme database... Please wait"):
        loading_placeholder = st.empty()
        loading_placeholder.info("⏳ First-time loading may take 30-60 seconds. Subsequent loads will be instant!")
        
        try:
            vectordb, eligibility_data, num_docs, from_cache = load_data()
            st.session_state.vectordb = vectordb
            st.session_state.eligibility_data = eligibility_data
            st.session_state.num_docs = num_docs
            st.session_state.data_loaded = True
            
            loading_placeholder.empty()
            if from_cache:
                st.sidebar.success(f"⚡ Loaded {num_docs} documents (from cache - instant!)")
            else:
                st.sidebar.success(f"✅ Loaded {num_docs} documents (database created)")
        except Exception as e:
            loading_placeholder.error(f"❌ Error loading RAG data: {e}")
            st.session_state.vectordb = None
            st.session_state.eligibility_data = {}
            st.session_state.num_docs = 0
else:
    st.sidebar.success(f"✅ {st.session_state.num_docs} documents ready")

# Use session state variables
vectordb = st.session_state.vectordb
eligibility_data = st.session_state.eligibility_data

# Left column: user inputs + OCR + mic
left, right = st.columns([1, 1])

with left:
    st.subheader("🧾 Upload Document (Aadhaar / PAN / Driving License)")
    uploaded_file = st.file_uploader("Upload Document Image", type=["jpg", "jpeg", "png"])

    extracted_text = ""
    auto_aadhaar_linked = False

    if uploaded_file is not None:
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Document", use_column_width=False, width=320)
            with st.spinner("Extracting text using OCR..."):
                extracted_text = pytesseract.image_to_string(image)
        except Exception as e:
            st.error(f"OCR failed: {e}")
            extracted_text = ""

        if extracted_text:
            st.subheader("🧾 Extracted Text")
            st.text_area("Extracted Text", extracted_text, height=180)
            doc_type = detect_document_type(extracted_text)
            st.success(f"🔍 Detected Document Type: {doc_type}")

            if doc_type == "Aadhaar":
                auto_aadhaar_linked = True
                st.info("Aadhaar detected – attempting to auto-fill profile fields")
                details = extract_aadhaar_details(extracted_text)

                if details.get("name"):
                    st.session_state["ocr_name"] = details["name"]
                if details.get("dob"):
                    try:
                        year = int(re.split(r"[/-]", details["dob"])[2])
                        # Use 2025 as current year per conversation constraints
                        st.session_state["ocr_age"] = max(18, 2025 - year)
                    except Exception:
                        pass
                if details.get("gender"):
                    st.session_state["ocr_gender"] = details["gender"]
                if details.get("aadhaar_number"):
                    st.session_state["ocr_aadhaar_num"] = details["aadhaar_number"]
                    st.success(f"Aadhaar Number: {details['aadhaar_number']}")

    st.markdown("---")
    st.subheader("🎤 Voice Input")
    language = st.radio("Select Language for Speech Recognition", ["English", "Hindi"], horizontal=True)
    if st.button("🎙️ Start Recording (Local mic required)"):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                st.info("Listening... please speak clearly into your microphone")
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=10)
            lang_code = "en-IN" if language == "English" else "hi-IN"
            try:
                voice_text = recognizer.recognize_google(audio, language=lang_code)
                st.success("Transcription:")
                st.write(voice_text)
                st.session_state["voice_query"] = voice_text
            except sr.UnknownValueError:
                st.error("Could not understand audio")
            except sr.RequestError as e:
                st.error(f"Speech recognition service failed: {e}")
        except Exception as e:
            st.error(f"Microphone error: {e}")

with right:
    st.subheader("🧑 Enter Your Details")
    # Auto-fill fields if OCR set them in session_state
    name = st.text_input("Name", value=st.session_state.get("ocr_name", "Ravi"))
    age = st.number_input("Age", min_value=18, max_value=100, value=st.session_state.get("ocr_age", 22))
    gender = st.selectbox("Gender", ["male", "female", "other"], index=["male", "female", "other"].index(st.session_state.get("ocr_gender", "male")))
    caste = st.text_input("Caste", "OBC")
    nationality = st.text_input("Nationality", "Indian")
    education = st.text_input("Education", "B.Sc. Agriculture")
    occupation = st.text_input("Occupation", "Farmer")
    income = st.number_input("Annual Income (₹)", min_value=0, max_value=10000000, value=100000)
    aadhaar = st.text_input("Aadhaar Number (optional)", value=st.session_state.get("ocr_aadhaar_num", ""))
    # show aadhaar-linked checkbox default from OCR detection (if file uploaded)
    aadhaar_linked = st.checkbox("Aadhaar Linked", value=st.session_state.get("ocr_aadhaar_num") is not None or auto_aadhaar_linked)
    llm_choice = st.selectbox("Select LLM", ["gemini", "grok"])

st.markdown("---")
query = st.text_area("💬 Describe your need or situation:", value=st.session_state.get("voice_query", "I need help for agriculture as I am a small farmer with family income 1,00,000."))

# =========================
# Find eligible schemes (button triggers existing logic)
# =========================
if st.button("🔍 Find Eligible Schemes"):
    if vectordb is None:
        st.error("Vector DB is not loaded – cannot run retrieval. Check logs and files.")
    else:
        # Store current user info for history lookup
        st.session_state["current_user_name"] = name
        st.session_state["current_user_aadhaar"] = aadhaar
        
        with st.spinner("Analyzing and reasoning eligibility..."):
            client_profile = {
                "name": name,
                "age": age,
                "gender": gender,
                "caste": caste,
                "nationality": nationality,
                "education": education,
                "occupation": occupation,
                "income": income,
                "aadhaar": aadhaar,
                "aadhaar_linked": aadhaar_linked
            }

            # Get top schemes based on query
            top_schemes = get_top_schemes_from_query(query)
            eligible_schemes, reasoning = filter_eligible_schemes(client_profile, top_schemes, eligibility_data, llm_choice)

        # Save to history
        history_entry = {
            "user_id": get_user_id(name, aadhaar),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": query,
            "profile": client_profile,
            "eligible_schemes": eligible_schemes
        }
        save_user_history(history_entry)

        if eligible_schemes:
            st.success(f"✅ Found {len(eligible_schemes)} eligible scheme(s)! (Saved to history)")
            for scheme in eligible_schemes:
                st.subheader(f"📘 {scheme}")
                st.markdown(f"**Reasoning:** {reasoning[scheme]['reasoning']}")

                with st.expander("📄 Scheme Summary"):
                    context = retrieve_context(f"Summary of {scheme} scheme")
                    llm = get_llm_instance(llm_choice)
                    if llm is None:
                        st.error("LLM not available for summarization")
                    else:
                        prompt = f"Summarize the {scheme} scheme in simple language:\n\n{context}"
                        try:
                            resp = llm.invoke(prompt)
                            st.write(resp.content)
                        except Exception as e:
                            st.error(f"Error summarizing {scheme}: {e}")
        else:
            st.warning("No schemes match your eligibility and query.")

# Footer / notes
st.markdown("---")
st.caption("Notes: 1) Speech recognition requires local microphone access and may not work on Streamlit Cloud. 2) If LLM init fails, check API keys in the sidebar; fallback keys will be used if configured. 3) Search history is saved automatically for each query. 4) Database loads instantly after first initialization.")

# Optional: Add button to rebuild database
with st.sidebar.expander("⚙️ Advanced Settings"):
    if st.button("🔄 Rebuild Vector Database"):
        import shutil
        if os.path.exists(DB_DIR):
            shutil.rmtree(DB_DIR)
        st.session_state.data_loaded = False
        st.rerun()