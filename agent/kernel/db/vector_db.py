# In agent/db/vector_db.py
import config

import uuid
import logging
from typing import List, Dict, Any

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorDB:
    """
    Handles interactions with the Qdrant vector database for storing and retrieving memories.
    """
    
    def __init__(self, collection_name: str = "agent_ltm"):
        """
        Initializes the VectorDB, connecting to Qdrant and loading the embedding model.

        Args:
            collection_name (str): The name of the collection to use in Qdrant.
        """
        try:
            self.client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
            logger.info(f"Successfully connected to Qdrant at {config.QDRANT_HOST}:{config.QDRANT_PORT}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.collection_name = collection_name
        self.vector_size = self.embedding_model.get_sentence_embedding_dimension()

        self._ensure_collection_exists()

    def _encode(self, text: str) -> list:
        # SentenceTransformers uses tqdm progress bars by default which corrupts stdout IPC
        return self.embedding_model.encode(text, show_progress_bar=False).tolist()

    def _ensure_collection_exists(self):
        """
        Checks if the collection exists in Qdrant and creates it if it doesn't.
        """
        try:
            self.client.get_collection(collection_name=self.collection_name)
            logger.info(f"Collection '{self.collection_name}' already exists.")
        except Exception:
            logger.info(f"Collection '{self.collection_name}' not found. Creating it...")
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE),
            )
            logger.info(f"Collection '{self.collection_name}' created successfully.")

    def add_memory(self, text: str, metadata: Dict[str, Any] = None) -> str:
        """
        Embeds a piece of text and stores it as a memory in the vector database.
        The `memory.py` module is responsible for ensuring the 'text' is in the metadata.
        """
        if not text.strip():
            logger.warning("Attempted to add an empty memory. Skipping.")
            return None

        payload = metadata if metadata is not None else {}
        point_id = payload.get('id') or str(uuid.uuid4())
        payload['id'] = point_id

        vector = self._encode(text)

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
            ],
            wait=True
        )
        logger.info(f"Added new memory with ID: {point_id}")
        return point_id
    def get_recent_memories(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieves recent memories from the vector database using the scroll API.
        Sorts them by timestamp_utc descending.
        """
        try:
            records, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=100, # Fetch a batch to sort
                with_payload=True,
                with_vectors=False
            )
            memories = [record.payload for record in records if record.payload]
            memories.sort(key=lambda x: x.get('timestamp_utc', ''), reverse=True)
            return memories[:limit]
        except Exception as e:
            logger.error(f"Failed to fetch recent memories from Qdrant: {e}")
            return []

    def search(self, query_text: str, num_results: int = 5, filter_kwargs: Dict[str, Any] = None) -> List[models.ScoredPoint]:
        """
        Searches for memories that are semantically similar to the query text.

        Args:
            query_text (str): The text to search for.
            num_results (int): The maximum number of similar memories to return.
            filter_kwargs (Dict[str, Any], optional): Key-value pairs to filter payload metadata.

        Returns:
            List[models.ScoredPoint]: A list of Qdrant ScoredPoint objects, which
                                     include the payload, score, id, and vector.
        """
        if not query_text.strip():
            logger.warning("Attempted to search with an empty query. Skipping.")
            return []

        query_vector = self._encode(query_text)
        
        query_filter = None
        if filter_kwargs:
            must_conditions = [
                models.FieldCondition(key=col, match=models.MatchValue(value=val))
                for col, val in filter_kwargs.items()
            ]
            query_filter = models.Filter(must=must_conditions)
        
        # Use the correct Qdrant 1.x API
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=num_results,
            with_payload=True
        ).points
        
        logger.info(f"Found {len(search_results)} relevant memories for query: '{query_text[:50]}...'")
        
        # Ensure payload has ID
        for hit in search_results:
            if hit.payload is not None:
                hit.payload['id'] = hit.id

        # We return the raw search results from the client directly.
        # This list contains ScoredPoint objects, which is what memory.py expects.
        return search_results

# Example usage for direct testing (updated to reflect the new return type)
if __name__ == '__main__':
    print("Running VectorDB standalone test...")
    try:
        vdb = VectorDB()
        
        print("\n--- Adding Memories ---")
        vdb.add_memory("The sky is blue.", {"source": "observation", "text": "The sky is blue."})
        vdb.add_memory("Photosynthesis is a process.", {"source": "web_search", "text": "Photosynthesis is a process."})
        vdb.add_memory("The agent used a tool.", {"source": "internal_log", "text": "The agent used a tool."})
        
        print("\n--- Searching for 'plant biology' ---")
        search_results = vdb.search("plant biology", num_results=2)
        
        # The loop is updated to handle ScoredPoint objects
        for hit in search_results:
            print(f"Score: {hit.score:.4f} - Payload: {hit.payload}")
            
        print("\nStandalone test completed successfully.")

    except Exception as e:
        print(f"An error occurred during the standalone test: {e}")