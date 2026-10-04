# agent/config.py
from uuid import uuid4
from langchain_core.runnables import RunnableConfig
from langchain_core.tracers import LangChainTracer
from src.ai_manager.callbacks import MetricCallBacks
from src.ai_manager.settings import ai_settings


class RunnableConfigBuilder:



    @staticmethod
    def build_config(customer_id: str, mobile: str, conversation_id: str | None = None) -> RunnableConfig:
        thread_id = f"{customer_id}:{conversation_id}" if conversation_id else str(customer_id)
        return {
            "run_id": uuid4(),
            "tags": ai_settings.AGENT_TAGS,
            "recursion_limit": ai_settings.AGENT_RECURSION_LIMIT,
            "callbacks": [
                MetricCallBacks(),
                LangChainTracer(project_name=ai_settings.LANGSMITH_PROJECT),
            ],
            "configurable": {
                "thread_id": thread_id,
                "user": {"customer_id": str(customer_id), "mobile": mobile},
            },
        }

