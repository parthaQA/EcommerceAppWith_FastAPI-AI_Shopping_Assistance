from langchain_redis.cache import RedisSemanticCache
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langgraph.checkpoint.postgres import PostgresSaver
from langsmith import traceable
from psycopg_pool import ConnectionPool
import os
from dotenv import load_dotenv
from mem0 import Memory

from src.ai_manager.ai_manager import build_chat_model
from src.ai_manager.mem0_config import config
from src.utils.settings import settings


class DBManager:

    load_dotenv()

    REDIS_URL = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379"
    )

    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


    REWRITE_SYSTEM_PROMPT = """You rewrite user queries for a vector search / retrieval system used in an e-commerce return, refund, and replacement policy support system.

    Rules:
    - Resolve pronouns and references using the conversation history (e.g. "it", "that", "the second one", "what about last month").
    - Remove conversational filler ("hey", "can you tell me", "thanks", "ok and").
    - Make the query specific, standalone, and self-contained — it must make sense without the prior conversation.
    - Normalize terminology to match policy language: "ordered date" -> "delivery date", "broken/cracked/faulty" -> "damaged" or "defective", "swap/exchange" -> "replacement", "money back" -> "refund", "cancel order" -> "cancellation".
    - If the query concerns wrong item, missing item, damaged item, defective item, size/variant issue, or change of mind, keep that distinction explicit in the rewrite — these are handled as separate policy sections.
    - Preserve the original intent exactly. Do NOT answer the question or add new information not implied by the conversation.
    - Output ONLY the rewritten query text. No preamble, no quotes, no explanation."""

    DATABASE_URL = os.getenv("DB_CONNECTION")
    RAG_DATABASE_URL = os.getenv("RAG_DB_URL")

    pool = ConnectionPool(conninfo=str(DATABASE_URL),
                              kwargs={"autocommit": True},
                              )

    checkpointer = PostgresSaver(pool)


    @classmethod
    def get_checkpointer(cls):
        return cls.checkpointer.setup()



    @staticmethod
    def initialize_mem0_memory():

        mem = Memory.from_config(config)
        return mem


    @staticmethod
    def insert_into_mem0_db(messages, customer_id):

        print("customer_id in insert_into_mem0_db :", customer_id)
        mem = DBManager.initialize_mem0_memory()

        try:
            result = mem.add(messages, user_id=customer_id)
            return result

        except Exception as e:
            print("Error inserting into mem0 database:", str(e))
            return None




    @staticmethod
    def retrieve_from_mem0_db(query, customer_id):

        mem = DBManager.initialize_mem0_memory()

        try:
            result = mem.search(
                query,
                filters={
                    "user_id": customer_id
                }
            )

            return result

        except Exception as e:
            print(
                "Error retrieving from mem0 database:",
                str(e)
            )
            return None


    @staticmethod
    def setup_vector_store():

        vectorstore = PGVector(
            embeddings=DBManager.embedding_model,
            collection_name="refund/return policy",
            connection=DBManager.RAG_DATABASE_URL,
        )

        return vectorstore


    @staticmethod
    @traceable
    def rewrite_query(messages: list) -> str:
        """
        Rewrites the latest user message into a standalone, retrieval-optimized query
        using prior conversation turns for context.
        """
        current_query = messages[-1].content
        history = messages[-7:-1] if len(messages) > 1 else []

        history_text = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
            for m in history
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", DBManager.REWRITE_SYSTEM_PROMPT),
            ("human", "Conversation history:\n{history}\n\nOriginal query: {query}\n\nRewritten query:")
        ])
        llm_chat = build_chat_model()

        chain = prompt | llm_chat
        response = chain.invoke({
            "history": history_text if history_text else "(none)",
            "query": current_query
        })

        rewritten = response.content.strip()

        # Small local models often wrap output in quotes or add a leading label — clean that up
        rewritten = rewritten.strip('"').strip("'")
        if rewritten.lower().startswith("rewritten query:"):
            rewritten = rewritten.split(":", 1)[1].strip()

        # Fallback: if the model returns something empty or clearly broken, use the original query
        if not rewritten or len(rewritten) < 3:
            return current_query

        return rewritten

    _rag_cache = None

    @staticmethod
    def get_rag_cache():
        if DBManager._rag_cache is None:
            DBManager._rag_cache = RedisSemanticCache(
                redis_url=DBManager.REDIS_URL,
                embeddings=DBManager.embedding_model,
                distance_threshold=0.08,
                name="rag_context_cache",
                ttl=3600
            )

        return DBManager._rag_cache
