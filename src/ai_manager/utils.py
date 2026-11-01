# from src.ai_manager.ai_manager import llm_chat
#
#
import os
import hashlib
import json
from dotenv import load_dotenv
import cohere
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.ai_manager.dtos import ToolResult

load_dotenv()

cohere_api_key = os.getenv("COHERE_API_KEY")



class Utils:

    _MAX_HISTORY = 4

    @staticmethod
    def rerank_query_response(query, document):

        cohere_client = cohere.Client(api_key=cohere_api_key)

        response = cohere_client.rerank(
            model="rerank-v3.5",
            query=query,
            documents=[doc.page_content for doc in document],
            top_n=3,
            return_documents=True,
        )

        return response


    @staticmethod
    def get_rag_pipeline_version(score_threshold, rerank_threshold, k, reranker):
        config = {"score_threshold": score_threshold,
              "rerank_threshold": rerank_threshold,
              "k": k,
              "reranker": reranker
              }

        RAG_PIPELINE_VERSION = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        print("rag pipeline version :",RAG_PIPELINE_VERSION)
        return RAG_PIPELINE_VERSION



    @staticmethod
    def get_customer_id(config: RunnableConfig) -> str:
        try:
            return str(config["configurable"]["user"]["customer_id"])
        except (KeyError, TypeError):
            raise HTTPException(401, "Authentication required")

    @staticmethod
    def build_chat_history(messages):
        last_human = max(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)),
            default=0,
        )
        current_turn = messages[last_human:]

        previous = [
            m for m in messages[:last_human]
            if isinstance(m, (HumanMessage, AIMessage))
               and not getattr(m, "tool_calls", None)
               and str(m.content).strip()
        ]
        return previous[-Utils._MAX_HISTORY:] + current_turn


    @staticmethod
    def capture_error(code: str, message: str) -> ToolResult:
        return ToolResult(success=False, message=message, error_code=code)