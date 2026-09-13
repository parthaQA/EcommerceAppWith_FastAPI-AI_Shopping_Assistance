# from src.ai_manager.ai_manager import llm_chat
#
#
import os
import hashlib
import json
from dotenv import load_dotenv
import cohere

load_dotenv()

cohere_api_key = os.getenv("COHERE_API_KEY")

class Utils:
#
#     @staticmethod
#     def normalize_memory(query: str) -> str:
#
#         prompt = create_intent_prompt(query)
#
#         response = llm_chat.invoke(prompt)
#
#         return response.content.strip()





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
