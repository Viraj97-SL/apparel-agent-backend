import os
import logging
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

load_dotenv()
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found.")

GEMINI_WORKER_MODEL = os.getenv("GEMINI_WORKER_MODEL", "gemini-2.5-flash")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
INDEX_PATH = os.path.join(project_root, "faiss_index")


def create_rag_chain():
    """RAG chain for policy/brand questions. LLM: Gemini Flash, Embeddings: HuggingFace MiniLM."""
    logger.info("Initializing RAG chain (Gemini Flash + HuggingFace MiniLM)...")

    llm = ChatGoogleGenerativeAI(
        model=GEMINI_WORKER_MODEL,
        temperature=0.0,
        google_api_key=GOOGLE_API_KEY,
    )

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    index_file = os.path.join(INDEX_PATH, "index.faiss")
    if not os.path.exists(index_file):
        logger.warning("FAISS index not found at %s — RAG disabled", index_file)
        return None

    try:
        db = FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
    except Exception as e:
        logger.warning("Failed to load FAISS index: %s — RAG disabled", e)
        return None
    retriever = db.as_retriever(search_kwargs={"k": 3})

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    prompt = ChatPromptTemplate.from_template("""
You are a helpful customer service assistant for Pamorya, a premium Sri Lankan apparel store.
Answer the user's question based only on the context below.
For greetings ("hi", "thanks"), respond warmly and briefly.
If the context doesn't cover the question, say "I don't have that information — please contact us directly."

CONTEXT:
{context}

QUESTION: {input}

ANSWER:""")

    rag_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    logger.info("RAG chain created.")
    return rag_chain
