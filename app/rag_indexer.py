import os
import logging
from dotenv import load_dotenv

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

DATA_PATH = os.path.join(project_root, "data")
INDEX_PATH = os.path.join(project_root, "faiss_index")

def create_vector_store():
    logger.info("Loading documents from: %s", DATA_PATH)
    loader = DirectoryLoader(
        DATA_PATH,
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()

    if not documents:
        logger.error("No .txt files found in %s", DATA_PATH)
        return

    logger.info("Loaded %d document(s)", len(documents))

    splitter = RecursiveCharacterTextSplitter(
        separators=["---", "\n\n", "\n"],
        chunk_size=1000,
        chunk_overlap=200,
    )
    docs = splitter.split_documents(documents)
    logger.info("Split into %d chunks", len(docs))

    logger.info("Embedding with HuggingFace all-MiniLM-L6-v2...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    db = FAISS.from_documents(docs, embeddings)
    db.save_local(INDEX_PATH)
    logger.info("FAISS index saved to %s", INDEX_PATH)


if __name__ == "__main__":
    create_vector_store()
