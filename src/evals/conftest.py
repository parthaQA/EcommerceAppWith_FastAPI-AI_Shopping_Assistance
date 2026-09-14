import csv
import json
import os
from pathlib import Path

from deepeval.test_case import ToolCall

os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "1800"
os.environ["DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE"] = "1800"      # NEW — overall task timeout
os.environ["DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE"] = "1800"

import pytest
from langchain_core.messages import HumanMessage
from deepeval.models import OllamaModel
from deepeval.dataset import Golden


BASE_DIR = Path(__file__).resolve().parent
GOLDENS_DIR = BASE_DIR / "goldens"

GENERATOR_GOLDENS = GOLDENS_DIR / "generator_goldens.csv"
TOOL_CALL_GOLDENS = GOLDENS_DIR / "tool_goldens.csv"
RETRIEVAL_GOLDENS = GOLDENS_DIR / "retrieval_goldens.csv"


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

def load_csv_rows(file_name):
    csv_path = GOLDENS_DIR / file_name

    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def pytest_generate_tests(metafunc):

    # Retrieval goldens
    if "retrieval_golden" in metafunc.fixturenames:
        rows = load_csv_rows(RETRIEVAL_GOLDENS)

        metafunc.parametrize(
            "retrieval_golden",
            rows,
            indirect=True,
        )

    # Generator goldens
    if "generator_golden" in metafunc.fixturenames:
        rows = load_csv_rows(GENERATOR_GOLDENS)

        metafunc.parametrize(
            "generator_golden",
            rows,
            indirect=True,
        )

    # Tool goldens
    if "tool_golden" in metafunc.fixturenames:
        rows = load_csv_rows(TOOL_CALL_GOLDENS)

        metafunc.parametrize(
            "tool_golden",
            rows,
            indirect=True,
        )


@pytest.fixture(scope="function")
def retrieval_golden(request):
    row = request.param

    return Golden(
        input=row["input"],
        expected_output=row["expected_output"],
    )


@pytest.fixture(scope="function")
def generator_golden(request):
    row = request.param

    return Golden(
        input=row["input"],
        expected_output=row["expected_output"],
    )


@pytest.fixture(scope="function")
def tool_golden(request):
    row = request.param

    raw_params = row.get("input_parameters", "").strip()

    input_parameters = (
        json.loads(raw_params)
        if raw_params
        else None
    )

    return Golden(
        input=row["input"],
        expected_tools=[
            ToolCall(
                name=row["expected_tools"],
                input_parameters=input_parameters,
            )
        ],
    )