import os

from deepeval.test_case import ToolCall

os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "1800"
os.environ["DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE"] = "1800"      # NEW — overall task timeout
os.environ["DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE"] = "1800"

import pytest
from langchain_core.messages import HumanMessage
from deepeval.models import OllamaModel
from deepeval.dataset import Golden

@pytest.fixture(scope="session")
def judge_model():
    return OllamaModel(
        model="qwen2.5:7b-instruct",
        base_url="http://localhost:11434",
        temperature=0 , # deterministic scoring, important for a judge model
    )

@pytest.fixture
def make_state():
    """Factory fixture — builds a minimal, realistic state dict for any node."""
    def _make_state(user_input: str, **extra):
        state = {
            "messages": [HumanMessage(content=user_input)],
            "eval_mode": True,
        }
        state.update(extra)
        return state
    return _make_state

@pytest.fixture
def retrieval_goldens():
    return [
        Golden(
            input="If I return a product within 3 days of delivery, how much refund will I get?",
            expected_output="You will get a 100% refund of the product amount, since the return is within 5 days of delivery.",
        ),
        Golden(
            input="I want to return a product 7 days after delivery. What refund can I expect?",
            expected_output="You will get a 50% refund of the product amount, since the return is more than 5 days but within 10 days from delivery.",
        ),
    ]

@pytest.fixture
def tool_goldens():
    return [
        Golden(
            input="Add to cart 1 quantity of potato",
            expected_tools=[ToolCall(name="add_product_to_cart", input_parameters={"product_name" :"potato", "quantity": 1})],
        ),
        Golden(
            input="get my cart details?",
            expected_tools=[ToolCall(name="get_cart")],
        ),
        Golden(
            input="Search potato",
            expected_tools=[ToolCall(name="search_product",
                                     input_parameters={"name" :"potato"})],

        ),
    ]