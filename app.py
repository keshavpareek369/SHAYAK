
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
