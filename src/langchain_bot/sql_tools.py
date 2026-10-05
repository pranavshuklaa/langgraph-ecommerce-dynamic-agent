from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "ecommerce.db"


def get_database():
    return SQLDatabase.from_uri(
        f"sqlite:///{DB_PATH}"
    )


def get_sql_tools():
    db = get_database()

    model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    )

    toolkit = SQLDatabaseToolkit(
        db=db,
        llm=model
    )

    return toolkit.get_tools()