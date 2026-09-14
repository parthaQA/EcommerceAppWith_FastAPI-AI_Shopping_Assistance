import pytest
from deepeval.evaluate import assert_test
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, ToolCall, ToolCallParams

from src.ai_manager.graph_orchestrator import GraphOrchestrator


def build_generator_test_case(golden, make_state):
    state = make_state(golden.input)

    retrieval_result = GraphOrchestrator.rag_node(state)
    state.update(retrieval_result)  # merges retrieved_context + retrieved_chunks into state

    # Step B: real generation — call_model reads state["retrieved_context"]
    generation_result = GraphOrchestrator.call_model(state)
    ai_message = generation_result["messages"][-1]

    print("ai message :", ai_message.content)

    return LLMTestCase(
        input=golden.input,
        actual_output=ai_message.content,
        expected_output=golden.expected_output,
        retrieval_context=retrieval_result.get("retrieved_chunks", []),
    )

def build_tool_test_case(golden, make_state):
    state = make_state(golden.input)
    generation_result = GraphOrchestrator.call_model(state)
    ai_message = generation_result["messages"][-1]

    tools_called = [
        ToolCall(name=tc["name"], input_parameters=tc.get("args", {}))
        for tc in getattr(ai_message, "tool_calls", [])
    ]
    return LLMTestCase(
        input=golden.input,
        actual_output=ai_message.content or "",
        tools_called=tools_called,
        expected_tools=golden.expected_tools,
    )


# def test_faithfulness(
#     generator_golden,
#     make_state,
#     judge_model,
# ):
#     test_case = build_generator_test_case(
#         generator_golden,
#         make_state,
#     )
#
#     metric = FaithfulnessMetric(
#         threshold=0.7,
#         model=judge_model,
#         async_mode=False,
#         truths_extraction_limit=4,
#         penalize_ambiguous_claims=True,
#         include_reason=True,
#         verbose_mode=True,
#     )
#
#     metric.measure(test_case)
#
#     print("ai message :", test_case.actual_output)
#     print("score :", metric.score)
#     print("reason :", metric.reason)
#     print("verdict :", metric.verdicts)
#
#     assert_test(test_case, [metric])



#
#
# def test_answer_relevancy(generator_golden , make_state, judge_model):
#     test_case = build_generator_test_case(generator_golden, make_state)
#
#     metric = AnswerRelevancyMetric(
#         threshold=0.7,
#         model=judge_model,
#         async_mode=False,
#         include_reason=True,  # keep this, essential for debugging
#         verbose_mode=True,
#     )
#     metric.measure(test_case)
#     print("verbose logs :", metric.verbose_logs)
#     print("score :", metric.score)
#     print("reason :", metric.reason)
#     print("verdict :", metric.verdicts)
#     print("verbose mode :", metric.verbose_mode)
#     print("tokens :", metric.input_tokens + metric.output_tokens)
#     assert_test(test_case, [metric])
#
#
#
def test_tool_correctness(tool_golden, make_state):
    test_case = build_tool_test_case(tool_golden, make_state)

    tool_name = tool_golden.expected_tools[0].name

    NAME_ONLY_TOOLS = {"get_cart"}

    if tool_name in NAME_ONLY_TOOLS:
        metric = ToolCorrectnessMetric(threshold=0.7)
    else:
        metric = ToolCorrectnessMetric(
            threshold=0.7,
            evaluation_params=[ToolCallParams.INPUT_PARAMETERS],
        )

    metric.measure(test_case)

    print("verbose logs", metric.verbose_logs)
    print("Tools called:", test_case.tools_called)
    print("Expected tools:", test_case.expected_tools)
    print("Score:", metric.score)
    print("Reason:", metric.reason)


    assert_test(test_case, [metric])