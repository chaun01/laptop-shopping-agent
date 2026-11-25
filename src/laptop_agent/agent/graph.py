"""The shopping agent: a single LangGraph agent with explicit guard, approval and output nodes.

    START -> input_guard --blocked--> END
                 |
               agent <--------------------------+------------------+
                 |  tool calls?                 |                  |
                 +--> place_order? -> approve --+ (declined)       |
                 |          (approved)  |                          |
                 |                      v                          |
                 +------------------> tools ------------------------+
                 |  no tool calls
                 v
            output_guard --ungrounded price (1 retry)--> agent
                 |
                END

Loop safety: a per-turn tool-round budget (MAX_TOOL_ROUNDS) forces a final answer, and the
graph-level recursion_limit is a hard stop. Memory: short-term via the checkpointer (thread_id),
long-term via user preferences in SQLite.
"""
import asyncio
import json
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import (AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage,
                                     ToolMessage, trim_messages)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from laptop_agent.agent.prompts import FORCE_ANSWER, PRICE_CORRECTION, resolve_system_prompt
from laptop_agent.config import get_settings
from laptop_agent.db.database import connect, get_preferences
from laptop_agent.guardrails.checks import (REFUSALS, check_input, check_output, classify_llm,
                                            tool_texts_from, validate_tool_call)
from laptop_agent.llm import get_chat_model
from laptop_agent.tools import ALL_TOOLS
from laptop_agent.tools.cart import call_cart

MAX_TOOL_ROUNDS = 6        # tool-calling rounds allowed per user turn
HISTORY_TOKENS = 6000      # short-term memory window sent to the model
HITL_TOOLS = {"place_order"}


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    preferences: dict
    tool_rounds: int
    correction: str | None
    correction_used: bool
    guard: dict


def _user_id(config) -> str:
    return config["configurable"]["user_id"]


def _current_turn(messages: list[AnyMessage]) -> list[AnyMessage]:
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    return messages[last_human:]


# ------------------------------------------------------------------ nodes
async def input_guard(state: AgentState, config) -> Command[Literal["agent", "__end__"]]:
    last = state["messages"][-1]
    prev_ai = next((m.text for m in reversed(state["messages"][:-1]) if isinstance(m, AIMessage) and m.text), "")
    parallel = get_settings().parallel_input_guard
    # Deterministic layers (length, PII, regex) always run here; the LLM classifier either runs here
    # (sequential) or concurrently with the agent's first model call (parallel, saves ~2s per turn).
    verdict = await asyncio.to_thread(check_input, last.text, not parallel, prev_ai)
    reset = {"tool_rounds": 0, "correction": None, "correction_used": False,
             "guard": {"input": verdict.label, "pii": verdict.pii_found, "reason": verdict.reason,
                       "llm_pending": parallel and verdict.allowed, "context": prev_ai[-600:]}}
    if not verdict.allowed:
        return Command(goto=END, update={**reset, "messages": [AIMessage(REFUSALS[verdict.label],
                                                                         name="guardrail")]})
    update = dict(reset)
    if verdict.pii_found:   # overwrite the stored message so PII never reaches the LLM, logs or traces
        update["messages"] = [HumanMessage(verdict.clean_text, id=last.id)]
    with connect() as conn:
        update["preferences"] = get_preferences(conn, _user_id(config))
    return Command(goto="agent", update=update)


async def agent(state: AgentState, config) -> dict:
    s = get_settings()
    history = trim_messages(state["messages"], max_tokens=HISTORY_TOKENS, strategy="last",
                            token_counter="approximate", start_on="human", include_system=False)
    prompt_text, managed_prompt = await asyncio.to_thread(
        resolve_system_prompt, s.prompt_version, state.get("preferences", {}))
    msgs = [SystemMessage(prompt_text)] + history
    llm_cfg = {"tags": ["agent_answer"], "metadata": {"langfuse_prompt": managed_prompt} if managed_prompt else {}}
    rounds = state.get("tool_rounds", 0)
    if state.get("correction"):
        msgs.append(SystemMessage(state["correction"]))
    if rounds >= MAX_TOOL_ROUNDS:
        msgs.append(SystemMessage(FORCE_ANSWER))
        model_call = get_chat_model().with_config(**llm_cfg).ainvoke(msgs, config)          # no tools -> must answer
    else:
        model_call = get_chat_model(ALL_TOOLS).with_config(**llm_cfg).ainvoke(msgs, config)

    guard = dict(state.get("guard", {}))
    if guard.pop("llm_pending", False):
        # Parallel input guard: classifier and agent run concurrently; a block discards the agent's
        # response before any tool executes, so safety is unchanged and latency drops.
        user_text = history[-1].text if history else ""
        (label, reason), response = await asyncio.gather(
            asyncio.to_thread(classify_llm, user_text, guard.get("context", "")), model_call)
        guard.update(input=label, reason=reason)
        if label != "ok":
            return {"messages": [AIMessage(REFUSALS[label], name="guardrail")], "guard": guard,
                    "correction": None}
    else:
        response = await model_call
    return {"messages": [response], "correction": None, "guard": guard,
            "tool_rounds": rounds + (1 if response.tool_calls else 0)}


def route_after_agent(state: AgentState) -> Literal["approve", "tools", "output_guard"]:
    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return "output_guard"
    if any(tc["name"] in HITL_TOOLS for tc in last.tool_calls):
        return "approve"
    return "tools"


async def approve(state: AgentState, config) -> Command[Literal["tools", "agent"]]:
    """Human-in-the-loop: pause the graph and show the customer the cart before ordering."""
    last = state["messages"][-1]
    call = next(tc for tc in last.tool_calls if tc["name"] in HITL_TOOLS)
    cart = await call_cart("view_cart", {"user_id": _user_id(config)})
    decision = interrupt({"type": "confirm_order", "cart": cart,
                          "shipping_option": call["args"].get("shipping_option", "standard"),
                          "question": "Place this order? (yes/no)"})
    approved = str(decision).strip().lower() in {"yes", "y", "confirm", "ok", "true"}
    if approved:
        return Command(goto="tools")
    declined = [ToolMessage(json.dumps({"error": "customer declined the order confirmation"}),
                            tool_call_id=tc["id"], name=tc["name"]) for tc in last.tool_calls]
    return Command(goto="agent", update={"messages": declined})


async def _validate_then_run(request, execute):
    error = validate_tool_call(request.tool_call["name"], request.tool_call["args"])
    if error:
        return ToolMessage(json.dumps({"error": error}), tool_call_id=request.tool_call["id"],
                           name=request.tool_call["name"], status="error")
    return await execute(request)


tools_node = ToolNode(ALL_TOOLS, awrap_tool_call=_validate_then_run, handle_tool_errors=True)


async def output_guard(state: AgentState) -> Command[Literal["agent", "__end__"]]:
    last = state["messages"][-1]
    turn = _current_turn(state["messages"])
    # amounts may come from tools OR from the customer ("under $500"); both count as grounded
    sources = tool_texts_from(turn) + [m.text for m in turn if isinstance(m, HumanMessage)]
    check = check_output(last.text, sources)
    guard = {**state.get("guard", {}), "output_issues": check.issues}
    if check.ok:
        return Command(goto=END, update={"guard": guard})
    grounding = [i for i in check.issues if i.startswith("ungrounded_")]
    price_issue = next((i for i in grounding if i.startswith("ungrounded_prices")), None)
    if grounding and not state.get("correction_used"):
        # drop the bad answer and let the agent retry once with an explicit correction
        return Command(goto="agent", update={
            "messages": [RemoveMessage(id=last.id)], "correction_used": True, "guard": guard,
            "correction": PRICE_CORRECTION.format(amounts="; ".join(i.split(":", 1)[1] for i in grounding))})
    text = check.clean_text
    if "invented_coupon_code" in check.issues:
        text = ("I can't offer coupon codes or custom discounts. Current promotions are described in our "
                "payment policy (e.g. the 5% student discount).")
    elif price_issue:
        text += "\n\n_Note: please confirm the final price in your cart before checkout._"
    elif grounding:
        text += "\n\n_Note: please double-check the exact specs on the product details before buying._"
    return Command(goto=END, update={"guard": guard,
                                     "messages": [AIMessage(text, id=last.id, name="guardrail")]})


# ------------------------------------------------------------------ graph
def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("input_guard", input_guard)
    g.add_node("agent", agent)
    g.add_node("approve", approve)
    g.add_node("tools", tools_node)
    g.add_node("output_guard", output_guard)
    g.add_edge(START, "input_guard")
    g.add_conditional_edges("agent", route_after_agent)
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=checkpointer)
