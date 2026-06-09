from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from app.config import Settings
from app.state import ShoppingState
from app.prompts import SUPERVISOR_PROMPT, POLICY_WORKER_PROMPT, DATA_WORKER_PROMPT, RESPONSE_WORKER_PROMPT


def extract_json(text_or_list: Any) -> dict:
    if isinstance(text_or_list, list):
        text = "".join(str(t.get("text", "")) if isinstance(t, dict) else str(t) for t in text_or_list)
    else:
        text = str(text_or_list)
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


class ShoppingAssistant:
    """Student scaffold.

    Mục tiêu:
    - Dùng `Settings` để load config.
    - Dùng provider trong `src/provider/`.
    - Dùng embedding loader thật trong `src/rag/embeddings.py`.
    - Tự hoàn thiện phần còn lại: graph, routing, tool calling, RAG search, response synthesis.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()

        from provider import get_chat_model
        from app.data_access import ShoppingDataStore, build_data_tools
        from rag.embeddings import SentenceTransformerEmbeddings
        from rag.vector_store import ChromaPolicyStore
        
        self.llm = get_chat_model(self.settings)
        
        self.data_store = ShoppingDataStore(Path("data/order_customer_mock_data.json"))
        self.data_tools = build_data_tools(self.data_store)
        
        self.embedding_model = SentenceTransformerEmbeddings("sentence-transformers/all-MiniLM-L6-v2")
        self.policy_store = ChromaPolicyStore(
            persist_directory=Path("data/chroma_db"),
            embedding_model=self.embedding_model
        )
        self.policy_store.ensure_index(Path("data/policy_mock_vi.md"))
        
        self.graph = build_graph(self.llm, self.policy_store, self.data_tools)

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(Path("data/policy_mock_vi.md"))
            
        state: ShoppingState = {
            "question": question,
            "trace": []
        }
        
        result = self.graph.invoke(state)
        
        if trace_file:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, 'w', encoding='utf-8') as f:
                json.dump(result["trace"], f, ensure_ascii=False, indent=2)
                
        return {
            "route": result.get("route"),
            "policy_result": result.get("policy_result"),
            "data_result": result.get("data_result"),
            "final_answer": result.get("final_answer"),
            "trace": result.get("trace")
        }

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(Path("data/policy_mock_vi.md"))
            
        with open(test_file, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
            
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = []
        
        for i, case in enumerate(test_data):
            question = case["question"]
            trace_file = output_dir / f"trace_{i}.json"
            
            result = self.ask(question, trace_file=trace_file, rebuild_index=False)
            
            summary.append({
                "question": question,
                "expected": case.get("expected", {}),
                "actual_status": "ok",
                "final_answer": result["final_answer"],
                "trace_file": str(trace_file)
            })
            
        summary_file = output_dir / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        return {"total": len(test_data), "summary_file": str(summary_file)}


def build_graph(llm: Any, policy_store: Any, data_tools: list) -> Any:
    def supervisor_node(state: ShoppingState) -> dict:
        msg = SystemMessage(content=SUPERVISOR_PROMPT)
        human = HumanMessage(content=state["question"])
        response = llm.invoke([msg, human])
        
        try:
            route = extract_json(response.content)
        except Exception:
            route = {"status": "clarification_needed", "needs_policy": False, "needs_data": False, "clarification_question": "Sorry, I could not parse the routing decision."}
            
        return {
            "route": route,
            "trace": [{"node": "supervisor", "output": route}]
        }

    def worker_1_policy_node(state: ShoppingState) -> dict:
        query = state["question"]
        hits = policy_store.search(query, top_k=4)
        chunks_text = json.dumps(hits, ensure_ascii=False)
        
        prompt = f"{POLICY_WORKER_PROMPT}\n\nSearch Results:\n{chunks_text}"
        msg = SystemMessage(content=prompt)
        human = HumanMessage(content=query)
        response = llm.invoke([msg, human])
        
        try:
            res = extract_json(response.content)
        except Exception:
            res = {"status": "ok", "summary": response.content, "facts": [], "citations": []}
            
        return {
            "policy_result": res,
            "trace": [{"node": "worker_1_policy", "hits": hits, "output": res}]
        }

    def worker_2_data_node(state: ShoppingState) -> dict:
        llm_with_tools = llm.bind_tools(data_tools)
        msg = SystemMessage(content=DATA_WORKER_PROMPT)
        human = HumanMessage(content=state["question"])
        
        messages = [msg, human]
        tool_calls_trace = []
        
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        while hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_obj = next((t for t in data_tools if t.name == tool_name), None)
                if tool_obj:
                    tool_result = tool_obj.invoke(tool_args)
                else:
                    tool_result = {"error": f"Tool {tool_name} not found"}
                    
                tool_calls_trace.append({"tool": tool_name, "args": tool_args, "result": tool_result})
                messages.append(ToolMessage(content=json.dumps(tool_result, ensure_ascii=False), tool_call_id=tool_call["id"]))
            
            response = llm.invoke(messages)
            
        try:
            res = extract_json(response.content)
        except Exception:
            res = {"status": "not_found", "summary": response.content, "facts": [], "missing_fields": [], "not_found_entities": []}
            
        return {
            "data_result": res,
            "trace": [{"node": "worker_2_data", "tool_calls": tool_calls_trace, "output": res}]
        }

    def worker_3_response_node(state: ShoppingState) -> dict:
        msg = SystemMessage(content=RESPONSE_WORKER_PROMPT)
        context = {
            "question": state.get("question"),
            "route": state.get("route"),
            "policy_result": state.get("policy_result"),
            "data_result": state.get("data_result"),
        }
        human = HumanMessage(content=json.dumps(context, ensure_ascii=False))
        response = llm.invoke([msg, human])
        
        content = response.content
        if isinstance(content, list):
            final_text = "".join(str(t.get("text", "")) if isinstance(t, dict) else str(t) for t in content)
        else:
            final_text = str(content)
            
        return {
            "final_answer": final_text,
            "trace": [{"node": "worker_3_response", "output": final_text}]
        }
        
    def route_after_supervisor(state: ShoppingState) -> list[str]:
        route = state.get("route", {})
        if route.get("status") == "clarification_needed":
            return ["worker_3_response"]
            
        destinations = []
        if route.get("needs_policy"):
            destinations.append("worker_1_policy")
        if route.get("needs_data"):
            destinations.append("worker_2_data")
            
        if not destinations:
            destinations.append("worker_3_response")
            
        return destinations

    graph = StateGraph(ShoppingState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("worker_1_policy", worker_1_policy_node)
    graph.add_node("worker_2_data", worker_2_data_node)
    graph.add_node("worker_3_response", worker_3_response_node)
    
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_after_supervisor, ["worker_1_policy", "worker_2_data", "worker_3_response"])
    
    graph.add_edge("worker_1_policy", "worker_3_response")
    graph.add_edge("worker_2_data", "worker_3_response")
    graph.add_edge("worker_3_response", END)
    
    return graph.compile()
