from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Cache the vector store so we only build/load it once per process.
_vector_store = None

ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = ROOT / "policies"
CHROMA_DIR = ROOT / "chroma_db"


def load_policy_documents() -> list[Document]:
    documents = []

    policy_files = sorted(POLICIES_DIR.glob("*.txt"))

    for policy_file in policy_files:
        loader = TextLoader(
            str(policy_file),
            encoding="utf-8"
        )

        loaded_documents = loader.load()

        for document in loaded_documents:
            document.metadata["source"] = policy_file.name

        documents.extend(loaded_documents)

    return documents


def split_documents(
    documents: list[Document]
) -> list[Document]:

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

    return splitter.split_documents(documents)


def get_vector_store():
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )

    # Reuse an existing Chroma database if it exists.
    if CHROMA_DIR.exists() and any(CHROMA_DIR.iterdir()):
        print("Loading existing Chroma vector store...")

        _vector_store = Chroma(
            collection_name="policy_documents",
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings
        )

        print("Loaded existing Chroma vector store.")

        return _vector_store

    # Otherwise build the vector store from the policy files.
    print("Loading policy documents...")

    documents = load_policy_documents()

    if not documents:
        raise FileNotFoundError(
            f"No policy files found in: {POLICIES_DIR}"
        )

    print(f"Loaded {len(documents)} policy documents.")

    chunks = split_documents(documents)

    print(f"Created {len(chunks)} policy chunks.")

    print("Creating Chroma vector store...")

    _vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="policy_documents",
        persist_directory=str(CHROMA_DIR)
    )

    print("Created Chroma vector store.")

    return _vector_store


@tool
def search_policies(query: str) -> str:
    """
    Search the e-commerce policy and FAQ documents.

    Use this tool only for policy/FAQ questions such as:
    returns, return windows, refunds, shipping,
    cancellation policy, and return shipping.

    Do not use this tool for user-specific information such as:
    order status, order history, payments, returns for a specific order,
    or account information.
    """

    vector_store = get_vector_store()

    documents = vector_store.similarity_search(
        query,
        k=4
    )

    if not documents:
        return "No relevant policy information was found."

    formatted_results = []

    for index, document in enumerate(documents, start=1):
        source = document.metadata.get(
            "source",
            "unknown"
        )

        formatted_results.append(
            f"[Result {index} | Source: {source}]\n"
            f"{document.page_content}"
        )

    return "\n\n".join(formatted_results)


def initialize_vector_store():
    """
    Initialize the policy vector store during application startup.
    """
    return get_vector_store()


__all__ = [
    "search_policies",
    "initialize_vector_store",
    "load_policy_documents",
    "split_documents",
    "get_vector_store",
]