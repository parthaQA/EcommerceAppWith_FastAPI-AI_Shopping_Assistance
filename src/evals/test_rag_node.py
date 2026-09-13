import pytest
from deepeval import assert_test
from deepeval.evaluate import AsyncConfig
from deepeval.metrics.dag import BinaryJudgementNode
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric, DeepAcyclicGraph, DAGMetric,
)
from src.ai_manager.graph_orchestrator import GraphOrchestrator
from src.evals.dag_criterias import RANGE_CHECK_CRITERIA


def build_retriever_test_case(golden, state):
    result = GraphOrchestrator.rag_node(state)
    return LLMTestCase(
        input=golden.input,
        actual_output="placeholder",  # retriever-only test, no generation involved
        expected_output=golden.expected_output,
        retrieval_context=result.get("retrieved_chunks", []),
    )




@pytest.mark.parametrize("golden_index", [0, 1])
def test_contextual_precision(golden_index, retrieval_goldens, make_state, judge_model):
    golden = retrieval_goldens[golden_index]
    state = make_state(golden.input)
    test_case = build_retriever_test_case(golden, state)

    metric = ContextualPrecisionMetric(threshold=0.7, model=judge_model, async_mode=False)
    assert_test(test_case, [metric])


@pytest.mark.parametrize("golden_index", [0, 1])
def test_contextual_recall(golden_index, retrieval_goldens, make_state, judge_model):
    golden = retrieval_goldens[golden_index]
    state = make_state(golden.input)
    test_case = build_retriever_test_case(golden, state)

    metric = ContextualRecallMetric(threshold=0.7, model=judge_model)
    assert_test(test_case, [metric])


@pytest.mark.parametrize("golden_index", [0, 1])
def test_contextual_relevancy(golden_index, retrieval_goldens, make_state, judge_model):
    golden = retrieval_goldens[golden_index]
    state = make_state(golden.input)
    test_case = build_retriever_test_case(golden, state)

    metric = ContextualRelevancyMetric(threshold=0.7, model=judge_model)
    assert_test(test_case, [metric])


@pytest.mark.range
@pytest.mark.parametrize("golden_index", [0, 1])
def test_range_aware_relevancy(golden_index, retrieval_goldens, make_state, judge_model):
    golden = retrieval_goldens[golden_index]
    state = make_state(golden.input)
    test_case = build_retriever_test_case(golden, state)
    range_check_evaluator = BinaryJudgementNode(
        criteria=RANGE_CHECK_CRITERIA,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
    )
    range_check_evaluator.add_verdict(verdict=True, score=10)
    range_check_evaluator.add_verdict(verdict=False, score=0)

    dag = DeepAcyclicGraph(root_nodes=[range_check_evaluator])

    metric =  DAGMetric(
        name="Range-Aware Relevancy",
        dag=dag,
        model=judge_model,
        threshold=0.7,
    )

    metric.measure(test_case)  # run it explicitly first, so verbose_logs gets populated
    print("verbose logs :", metric.verbose_logs)
    print("score :", metric.score)
    print("reason :", metric.reason)


    assert_test(test_case, [metric])