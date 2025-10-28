
import os
import json
import streamlit as st
from dotenv import load_dotenv
from langchain.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

# ===============================================
# CONFIGURATION
# ===============================================
load_dotenv()

JSON_PATH = "D:/gov-scheme-assistant-updated/threetry/schemes.json"
ELIGIBILITY_JSON_PATH = "D:/gov-scheme-assistant-updated/threetry/eligibility_summary-2.json"
DB_DIR = "rag_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ===============================================
# LOAD SCHEMES DATA
# ===============================================
@st.cache_resource
def load_data():
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

    return vectordb, eligibility_data, len(docs)

vectordb, eligibility_data, num_docs = load_data()
st.sidebar.success(f"✅ Loaded {num_docs} documents")

# ===============================================
# HELPER FUNCTIONS
# ===============================================
def retrieve_context(query, k=10):
    retriever = vectordb.as_retriever(search_kwargs={"k": k})
    results = retriever.get_relevant_documents(query)
    return "\n\n".join([r.page_content for r in results])

def get_llm_instance(llm_choice):
    if llm_choice.lower() == "grok":
        return ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=os.getenv("GROK_API_KEY"))
    elif llm_choice.lower() == "gemini":
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash-001", temperature=0)
    return None

def get_top_schemes_from_query(query, top_k=30, search_k=500):
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
    filtered, reasoning_results = [], {}
    llm = get_llm_instance(llm_choice)

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
        Base your judgment strictly on the scheme’s eligibility criteria — don't assume missing data.
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

        if "eligible: yes" in reasoning_text.lower():
            filtered.append(scheme)
        reasoning_results[scheme] = {"reasoning": reasoning_text}

    return filtered, reasoning_results

# ===============================================
# STREAMLIT UI
# ===============================================
st.title("Intelligent Government Scheme Assistant")
st.write("Find which government schemes you're eligible for — using RAG + LLM reasoning.")

with st.sidebar:
    st.header("🧍‍♂️ Enter Your Details")
    name = st.text_input("Name", "Ravi")
    age = st.number_input("Age", 18, 100, 22)
    gender = st.selectbox("Gender", ["male", "female", "other"])
    caste = st.text_input("Caste", "OBC")
    nationality = st.text_input("Nationality", "Indian")
    education = st.text_input("Education", "B.Sc. Agriculture")
    occupation = st.text_input("Occupation", "Farmer")
    income = st.number_input("Annual Income (₹)", 0, 1000000, 100000)
    aadhaar_linked = st.checkbox("Aadhaar Linked", True)
    llm_choice = st.selectbox("Select LLM", ["gemini", "grok"])

st.markdown("---")

query = st.text_area("💬 Describe your need or situation:", "I need help for agriculture as I am a small farmer with family income 1,00,000.")

if st.button("🔍 Find Eligible Schemes"):
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
            "aadhaar_linked": aadhaar_linked
        }

        top_schemes = get_top_schemes_from_query(query)
        eligible_schemes, reasoning = filter_eligible_schemes(client_profile, top_schemes, eligibility_data, llm_choice)

    if eligible_schemes:
        st.success(f"✅ Found {len(eligible_schemes)} eligible scheme(s)!")
        for scheme in eligible_schemes:
            st.subheader(f"📘 {scheme}")
            st.markdown(f"**Reasoning:** {reasoning[scheme]['reasoning']}")

            with st.expander("📄 Scheme Summary"):
                context = retrieve_context(f"Summary of {scheme} scheme")
                llm = get_llm_instance(llm_choice)
                prompt = f"Summarize the {scheme} scheme in simple language:\n\n{context}"
                try:
                    resp = llm.invoke(prompt)
                    st.write(resp.content)
                except Exception as e:
                    st.error(f"Error summarizing {scheme}: {e}")
    else:
        st.warning("No schemes match your eligibility and query.")
