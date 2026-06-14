# agent/kernel/db/graph_retriever.py
import logging
from agent.kernel.db.graph_db import GraphDB
from agent.kernel.db.vector_db import VectorDB
from agent.kernel.tracer import active_trace_storage, Tracer

logger = logging.getLogger(__name__)

def retrieve_connected(query_text: str, vector_results: list[dict], hops: int = 1) -> list[dict]:
    """
    For each vector hit, extracts its ID, finds connected entities in GraphDB,
    retrieves neighbor memories connected to those entities, and merges them.
    Deduplicates by ID and returns at most 15 items, vector hits first, neighbors after.
    """
    seen_ids = set()
    final_results = []
    
    # Deduplicate vector results first
    for hit in vector_results:
        memory_id = hit.get('id')
        if memory_id and memory_id not in seen_ids:
            seen_ids.add(memory_id)
            final_results.append(hit)
            
    try:
        gdb = GraphDB()
        vdb = VectorDB()
    except Exception as e:
        logger.error(f"Failed to initialize databases in graph_retriever: {e}")
        return final_results[:15]
        
    neighbor_ids = []
    
    for hit in final_results:
        memory_id = hit.get('id')
        if not memory_id:
            continue
            
        # Find all entities linked to this memory ID
        cypher = """
        MATCH (m:Memory {id: $memory_id})-[r]-(e:Entity)
        RETURN e.name AS entity_name
        """
        entities_res = gdb.query(cypher, {"memory_id": memory_id})
        
        for entity_rec in entities_res:
            entity_name = entity_rec.get("entity_name")
            if entity_name:
                # Get neighbors for the entity
                neighbors = gdb.get_neighbors(entity_name, limit=20)
                for n in neighbors:
                    n_id = n.get("memory_id")
                    if n_id and n_id not in seen_ids:
                        neighbor_ids.append(n_id)
                        
    # Retrieve payloads from Qdrant for neighbor IDs
    if neighbor_ids:
        # Deduplicate neighbor IDs to retrieve
        neighbor_ids = list(dict.fromkeys(neighbor_ids))
        try:
            records = vdb.client.retrieve(
                collection_name=vdb.collection_name,
                ids=neighbor_ids
            )
            for record in records:
                if record.payload:
                    # Ensure id is populated
                    record.payload['id'] = record.id
                    if record.id not in seen_ids:
                        seen_ids.add(record.id)
                        final_results.append(record.payload)
        except Exception as e:
            logger.error(f"Failed to retrieve neighbor payloads from Qdrant: {e}")
            
    # Log tracer event
    try:
        trace_id = getattr(active_trace_storage, "trace_id", None)
        if trace_id:
            tracer_inst = Tracer()
            tracer_inst.log_event(trace_id, "graph_retrieval", {
                "vector_hits": len(vector_results),
                "neighbors_added": len(final_results) - len(vector_results)
            })
    except Exception:
        pass
        
    return final_results[:15]
