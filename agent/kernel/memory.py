# In agent/components/memory.py
import logging
import os
import json
import uuid
import math
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Any
import asyncio
from pydantic import BaseModel, Field, ValidationError
from google import genai

from agent.kernel.db.vector_db import VectorDB
from agent.kernel.db.graph_db import GraphDB
import config # Import config to access the API key

# --- Configuration ---
RELEVANCE_THRESHOLD = 7  # Memories with a score >= 7 will be saved

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Pydantic Models for Relevance Assessment ---
class RelevanceAssessment(BaseModel):
    """Schema for the LLM's judgment on a memory's relevance."""
    reasoning: str
    title: str
    score: int = Field(..., ge=1, le=10)  # Score from 1 to 10


# --- Core Components ---
class MemoryRelevanceAssessor:
    """Uses a Gemini model to evaluate the long-term utility of a memory."""

    def __init__(self, gemini_client, model_name: str, agent_goals: List[str]):
        self.client = gemini_client
        self.model_name = model_name
        self.agent_goals_str = "\n".join(f"- {goal}" for goal in agent_goals)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return f"""You are an AI memory evaluation system. Your task is to determine if a given piece of information is worth saving to a long-term vector database for an autonomous agent.

**Agent's Long-Term Goals:**
{self.agent_goals_str}

**Evaluation Criteria:**
1.  **Novelty & Insight:** Is this new, surprising, or a non-obvious insight? Does it correct a previous misunderstanding? (Trivial, repetitive, or obvious statements are not valuable).
2.  **Goal-Relevance:** Does this information directly or indirectly help in achieving the agent's long-term goals?
3.  **Generalizability & Reusability:** Is this a specific, one-time observation, or is it a general principle, strategy, error pattern, or capability that can be applied to future, different tasks? (e.g., "The user prefers concise answers" is generalizable. "The command 'ls' outputted 'file1.txt' at 3 PM" is not).
4.  **Strategic Value:** Does this memory pertain to successful strategies, failed attempts (and why they failed), key constraints, or important user preferences?

**Your Task:**
Based on the criteria above, evaluate the provided memory. Respond ONLY with a single, valid JSON object containing three keys:
- "title": A very short, concise title summarizing the memory (max 5 words).
- "reasoning": A brief explanation for your score.
- "score": An integer from 1 to 10, where 1 is 'useless conversational filler' and 10 is 'critically important strategic information'.
"""

    def assess(self, memory_content: str) -> RelevanceAssessment:
        """Assesses the relevance of a memory and returns a score."""
        if not self.client:
            logger.error("[ERROR] Gemini client not provided to MemoryRelevanceAssessor.")
            return RelevanceAssessment(reasoning="Assessment failed: Gemini client not available.", score=1)

        prompt = f"{self.system_prompt}\n\n**Memory to Evaluate:**\n\"{memory_content}\""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                purpose="memory_scoring"
            )
            # Clean up the response, removing markdown backticks and other noise
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()

            assessment_data = RelevanceAssessment(**json.loads(cleaned_response))
            return assessment_data
        except (ValidationError, json.JSONDecodeError, AttributeError) as e:
            logger.error(f"[ERROR] LLM assessment parsing failed: {e}. Raw response: '{response.text}'")
            return RelevanceAssessment(reasoning=f"Assessment failed due to parsing error: {e}", score=1)
        except Exception as e:
            logger.error(f"[ERROR] LLM assessment failed with an unexpected error: {e}")
            return RelevanceAssessment(reasoning=f"Assessment failed: {e}", score=1)


class MemoryModule:
    """
    The agent's memory system, managing short-term, long-term, and structured knowledge.
    """

    # --- MODIFIED SECTION ---
    # The __init__ method now REQUIRES `gemini_client` to be passed in, for proper dependency injection.
    def __init__(self, gemini_client=None, model_name: str = None, stm_max_size: int = 20, agent_long_term_goals: List[str] = None):
        """
        Initializes the MemoryModule.

        Args:
            gemini_client: An initialized GenAI Client instance.
            model_name (str): Gemini model name to use for relevance assessment.
            stm_max_size (int): The maximum number of recent events to hold in Short-Term Memory.
            agent_long_term_goals (List[str]): A list of the agent's current long-term goals.
        """
        logger.info("Initializing MemoryModule...")

        try:
            self.vector_db = VectorDB()
            self.graph_db = GraphDB()
        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            raise

        self.stm = deque(maxlen=stm_max_size)

        if agent_long_term_goals is None:
            agent_long_term_goals = ["Serve the operational and strategic goals set by the Director."]

        # The internally created model is passed to the assessor.
        self.assessor = MemoryRelevanceAssessor(gemini_client=gemini_client, model_name=model_name, agent_goals=agent_long_term_goals)
        
        # Async assessment queue
        self.assessment_queue = asyncio.Queue()
        self.is_running = True

        logger.info(f"MemoryModule initialized with STM max size of {stm_max_size}.")

    async def _process_assessment_queue(self):
        """Background worker that continuously processes the LTM assessment queue."""
        logger.info("MemoryModule async assessment worker started.")
        while self.is_running:
            try:
                event_data = await self.assessment_queue.get()
                event_text = event_data.get("text", "").strip()
                
                # Terminal logging only per user request
                print(f"[SYSTEM ASYNC] Starting LTM assessment job for memory: '{event_text[:50]}...'")
                
                # We need to run the potentially blocking LLM call in an executor
                loop = asyncio.get_running_loop()
                assessment = await loop.run_in_executor(None, self.assessor.assess, event_text)
                
                print(f"[SYSTEM ASYNC] LTM Assessment complete. Score: {assessment.score}/10")
                logger.info(f"LTM Assessment Score: {assessment.score}/10. Reasoning: {assessment.reasoning}")

                if assessment.score >= RELEVANCE_THRESHOLD:
                    logger.info(f"DECISION: Memory is relevant. Saving to LTM (VectorDB).")
                    memory_id = str(uuid.uuid4())
                    event_data['id'] = memory_id
                    event_data['relevance_score'] = assessment.score
                    event_data['relevance_reasoning'] = assessment.reasoning
                    event_data['title'] = assessment.title
                    event_data['type'] = "episodic_event"
                    
                    # Intercept write under quarantine mode
                    if os.environ.get("GC7_MEMORY_QUARANTINE") == "1":
                        worker_id = os.environ.get("GC7_WORKER_ID", "default_worker")
                        quarantine_dir = os.path.join(config.DATA_DIR, "quarantine")
                        os.makedirs(quarantine_dir, exist_ok=True)
                        quarantine_file = os.path.join(quarantine_dir, f"{worker_id}.jsonl")
                        logger.info(f"QUARANTINE: Appending memory to {quarantine_file}")
                        try:
                            event_data["text"] = event_text
                            with open(quarantine_file, "a", encoding="utf-8") as q_f:
                                q_f.write(json.dumps(event_data) + "\n")
                        except Exception as e:
                            logger.error(f"Failed to write quarantined memory: {e}")
                    else:
                        # Offload vector DB insertion as well
                        await loop.run_in_executor(None, self.vector_db.add_memory, event_text, event_data)
                        
                        # GraphDB Entity Extraction & Edge Insertion (run in executor)
                        await loop.run_in_executor(None, self._extract_and_save_entities, memory_id, event_text)
                else:
                    logger.info(f"DECISION: Memory discarded from LTM. (Score {assessment.score} < Threshold {RELEVANCE_THRESHOLD})")
                
                self.assessment_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in async assessment worker: {e}", exc_info=True)

    def _extract_and_save_entities(self, memory_id: str, text: str):
        """Extracts at most 5 entities from the memory text and stores them in GraphDB."""
        try:
            prompt = f"""Extract at most 5 key entities (concepts, technologies, directories, files, or names) from the following text.
Respond with ONLY a valid JSON object containing a list under the key "entities". Example: {{"entities": ["Photosynthesis", "Plant"]}}.
Do not include any Markdown block or prefix.

Text:
{text}
"""
            # Use cheap model tier
            response = self.assessor.client.models.generate_content(
                model=self.assessor.model_name,
                contents=prompt,
                purpose="classification"
            )
            cleaned = response.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            entities = data.get("entities", [])
            for entity in entities[:5]:
                self.graph_db.add_entity_edge(memory_id, entity, "mentions")
        except Exception as e:
            logger.error(f"Failed to extract/save entities for memory {memory_id}: {e}")


    def add_event(self, event_data: Dict[str, Any]) -> None:
        """
        Adds a new event to the agent's memory. The event is added to STM, then
        placed in the async queue for LTM relevance evaluation.
        """
        event_text = event_data.get("text", "").strip()
        if not event_text:
            logger.warning("Attempted to add an event with empty text. Skipping.")
            return

        timestamp = datetime.now(timezone.utc)
        event_data['timestamp_utc'] = timestamp.isoformat()

        self.stm.append(event_data)
        logger.info(f"Added to STM: [{event_data.get('source', 'unknown')}] {event_text[:100]}...")

        # Skip LTM assessment for specific sensor/trivial tools
        if event_data.get("type") == "tool_executor":
            # Assuming event_text starts with something like "[tool_executor] Executed tool 'tool_name'" 
            # We can extract or just check if the name is in the text roughly 
            if any(f"'{tool}'" in event_text for tool in getattr(config, 'TRIVIAL_TOOLS', [])):
                logger.debug(f"Skipping LTM assessment for trivial tool event: {event_text[:50]}")
                return

        # Fire and forget: add to async queue for background processing
        try:
            self.assessment_queue.put_nowait(event_data.copy())
        except Exception as e:
             logger.error(f"Failed to queue memory for async assessment: {e}")

    def add_structured_knowledge(self, subject: str, relationship: str, obj: str) -> None:
        """Adds a structured piece of knowledge to the Knowledge Graph."""
        relationship_upper = relationship.upper().replace(" ", "_")
        self.graph_db.add_node_if_not_exists("Entity", {"name": subject})
        self.graph_db.add_node_if_not_exists("Entity", {"name": obj})
        self.graph_db.add_relationship_if_not_exists(
            start_node_label="Entity", start_node_pk="name", start_node_pv=subject,
            end_node_label="Entity", end_node_pk="name", end_node_pv=obj,
            relationship_type=relationship_upper
        )
        logger.info(f"Added to Knowledge Graph: ({subject})-[{relationship_upper}]->({obj})")

    def get_short_term_memories(self) -> List[Dict[str, Any]]:
        """Retrieves all current short-term memories."""
        return list(self.stm)

    def get_recent_long_term_memories(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retrieves the most recent additions to the Long-Term Memory (VectorDB) for UI display."""
        return self.vector_db.get_recent_memories(limit=limit)

    def get_episodic_memories(self, query: str, num_results: int = 2) -> List[Dict[str, Any]]:
        """Retrieves relevant episodic memories based on a query."""
        search_results = self.vector_db.search(query, num_results=num_results, filter_kwargs={"type": "episodic_event"})
        payloads = [result.payload for result in search_results]
        from agent.kernel.db.graph_retriever import retrieve_connected
        return retrieve_connected(query, payloads)

    def get_strategic_insights(self, query: str, num_results: int = 2) -> List[Dict[str, Any]]:
        """Retrieves strategic insights based on a query."""
        search_results = self.vector_db.search(query, num_results=num_results, filter_kwargs={"type": "strategic_insight"})
        payloads = [result.payload for result in search_results]
        from agent.kernel.db.graph_retriever import retrieve_connected
        return retrieve_connected(query, payloads)

    def get_relevant_context(self, task_description: str) -> Dict[str, Any]:
        """Gathers a comprehensive context for a given task from all memory systems."""
        stm_context = self.get_short_term_memories()
        
        episodic_count = getattr(config, 'LTM_RETRIEVAL_COUNT', 5)
        insight_count = getattr(config, 'DYNAMIC_INSIGHT_COUNT', 5)
        
        episodic_context = self.get_episodic_memories(task_description, num_results=episodic_count)
        strategic_context = self.get_strategic_insights(task_description, num_results=insight_count)
        return {
            "short_term_memory": stm_context,
            "episodic_memory": episodic_context,
            "strategic_insights": strategic_context
        }

    def close_connections(self):
        """Gracefully closes the database connections."""
        self.is_running = False
        self.graph_db.close()
        logger.info("MemoryModule database connections closed.")

def consolidate_memories(memory_manager) -> dict:
    """
    Consolidates similar memory records (cosine similarity > 0.95) by merging them
    and marking the originals as superseded. Exposes a tool-callable job.
    """
    try:
        # Scroll to get recent memories with vectors
        records, _ = memory_manager.vector_db.client.scroll(
            collection_name=memory_manager.vector_db.collection_name,
            limit=1000,
            with_payload=True,
            with_vectors=True
        )
    except Exception as e:
        logger.error(f"Failed to scroll records for memory consolidation: {e}")
        return {"merged": 0}

    # Filter out records that are already superseded
    active_records = [r for r in records if r.payload and "superseded_by" not in r.payload]
    
    def cosine_similarity(v1, v2):
        dot_product = sum(x * y for x, y in zip(v1, v2))
        norm_v1 = math.sqrt(sum(x * x for x in v1))
        norm_v2 = math.sqrt(sum(y * y for y in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    merged_count = 0
    superseded_ids = set()

    from qdrant_client import models
    from agent.kernel.tracer import active_trace_storage, Tracer

    for i in range(len(active_records)):
        r1 = active_records[i]
        if r1.id in superseded_ids:
            continue
            
        for j in range(i + 1, len(active_records)):
            r2 = active_records[j]
            if r2.id in superseded_ids:
                continue
                
            # Compute similarity
            if r1.vector and r2.vector:
                sim = cosine_similarity(r1.vector, r2.vector)
                if sim > 0.95:
                    logger.info(f"Consolidation: found high similarity ({sim:.4f}) between {r1.id} and {r2.id}")
                    
                    text1 = r1.payload.get("text", "")
                    text2 = r2.payload.get("text", "")
                    
                    # Merge their texts
                    prompt = f"""Merge the following two similar memory records into one coherent text summarizing both clearly.
Record 1:
{text1}

Record 2:
{text2}

Respond with ONLY the combined summary text. Do not include prefix or markdown blocks.
"""
                    try:
                        # Call cheap model tier
                        response = memory_manager.assessor.client.models.generate_content(
                            model=memory_manager.assessor.model_name,
                            contents=prompt,
                            purpose="summarization"
                        )
                        merged_text = response.text.strip()
                    except Exception as e:
                        logger.error(f"Failed to summarize merged memory: {e}")
                        continue

                    # Create new memory
                    new_id = str(uuid.uuid4())
                    new_payload = {
                        "id": new_id,
                        "text": merged_text,
                        "type": r1.payload.get("type", "episodic_event"),
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "merged_from": [r1.id, r2.id]
                    }
                    
                    try:
                        # Write the new merged memory to VectorDB
                        memory_manager.vector_db.add_memory(merged_text, new_payload)
                        
                        # Mark originals as superseded
                        r1.payload["superseded_by"] = new_id
                        r2.payload["superseded_by"] = new_id
                        
                        # Update original points in Qdrant
                        memory_manager.vector_db.client.upsert(
                            collection_name=memory_manager.vector_db.collection_name,
                            points=[
                                models.PointStruct(id=r1.id, vector=r1.vector, payload=r1.payload),
                                models.PointStruct(id=r2.id, vector=r2.vector, payload=r2.payload)
                            ]
                        )
                        
                        # Mark them locally in the loop to prevent reuse
                        superseded_ids.add(r1.id)
                        superseded_ids.add(r2.id)
                        merged_count += 1
                        
                        # Break inner loop to search for next un-superseded item
                        break
                    except Exception as e:
                        logger.error(f"Failed to upsert consolidated points in vector DB: {e}")
                        continue

    # Log tracer event
    try:
        trace_id = getattr(active_trace_storage, "trace_id", None)
        if trace_id:
            tracer_inst = Tracer()
            tracer_inst.log_event(trace_id, "memory_consolidation", {
                "merged_count": merged_count
            })
    except Exception:
        pass

    return {"merged": merged_count}


# Example usage for direct testing:
if __name__ == '__main__':
    print("Running MemoryModule standalone test...")

    # Mock the configuration for the test
    class MockConfig:
        GEMINI_API_KEY = "mock-api-key-for-testing"
    config = MockConfig()

    class MockGeminiClient:
        class MockModels:
            def generate_content(self, model, contents):
                class MockResponse:
                    def __init__(self, text):
                        self.text = text
                if "hello" in contents or "time is" in contents:
                    return MockResponse('{"reasoning": "This is conversational filler.", "score": 1, "title": "Conversational"}')
                else:
                    return MockResponse('{"reasoning": "This information is generally useful.", "score": 8, "title": "Useful Info"}')
        def __init__(self):
            self.models = self.MockModels()

    class MockVectorDB:
        def __init__(self): self.memories = []
        def add_memory(self, text, metadata):
            print(f"[MOCK VectorDB] Adding memory: {text}")
            self.memories.append({"text": text, "metadata": metadata})
        def search_with_payload(self, query, num_results):
            print(f"[MOCK VectorDB] Searching for: {query}")
            return [{"score": 0.9, "payload": m["metadata"]} for m in self.memories if "python" in m["text"]][:num_results]

    class MockGraphDB:
        def add_node_if_not_exists(self, label, props): pass
        def add_relationship_if_not_exists(self, **kwargs): pass
        def close(self): pass

    try:
        VectorDB = MockVectorDB
        GraphDB = MockGraphDB

        current_goals = [
            "Develop a more efficient memory management system.",
            "Understand and respond to user queries about software development patterns.",
            "Improve self-correction capabilities by learning from errors."
        ]
        
        # Now, initializing MemoryModule is much simpler.
        mock_client = MockGeminiClient()
        memory = MemoryModule(gemini_client=mock_client, model_name="mock-model", stm_max_size=5, agent_long_term_goals=current_goals)

        print("\n--- Testing with a list of potential memories ---")
        potential_memories = [
            {"text": "The user just said 'hello'.", "source": "director"},
            {"text": "The Decorator design pattern in Python allows adding new functionalities to an object without altering its structure.", "source": "search_tool"},
            {"text": "I encountered a 'KeyError' when accessing a dictionary in python. This can be prevented by using the .get() method with a default value.", "source": "introspection"},
            {"text": "The current time is 3:45 PM.", "source": "system"},
            {"text": "The command 'ls -l' failed because it was run in a Windows environment. The equivalent is 'dir'.", "source": "action_executor"}
        ]

        for mem_data in potential_memories:
            memory.add_event(mem_data)
            print("---")

        print("\n--- Retrieving Relevant Long-Term Memories for 'python programming errors' ---")
        ltm_results = memory.get_episodic_memories("python programming errors", num_results=3)
        print("Relevant LTM hits:")
        for mem in ltm_results:
            print(f"- Score: {mem['score']:.2f}, Content: {mem['payload']['text']}")

        memory.close_connections()
        print("\nStandalone test completed successfully.")

    except Exception as e:
        print(f"An error occurred during the standalone test: {e}")