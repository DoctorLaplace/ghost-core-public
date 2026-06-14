import os
import json
import logging
import config
from qdrant_client import QdrantClient, models
from neo4j import GraphDatabase, exceptions

logger = logging.getLogger(__name__)

QDRANT_COLLECTION_NAME = "agent_ltm"

def wipe_workspace(base_dir):
    try:
        path = os.path.join(base_dir, 'data', 'current_context.md')
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Workspace Scratchpad\n\n[Empty]")
        logger.info("Workspace scratchpad wiped successfully.")
    except Exception as e:
        logger.error(f"Failed to wipe workspace: {e}")

def wipe_goals(base_dir):
    try:
        path = os.path.join(base_dir, 'data', 'goals.json')
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
        logger.info("Goals wiped successfully.")
    except Exception as e:
        logger.error(f"Failed to wipe goals: {e}")

def wipe_all_databases(base_dir):
    logger.info("Initiating full system memory wipe...")
    wipe_workspace(base_dir)
    wipe_goals(base_dir)

    # Wipe Qdrant
    try:
        client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
        try:
            client.delete_collection(collection_name=QDRANT_COLLECTION_NAME)
        except Exception:
            pass # ignore if collection doesn't exist
            
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
        )
        logger.info("Qdrant collection wiped and recreated.")
    except Exception as e:
        logger.error(f"Error wiping Qdrant: {e}")

    # Wipe Neo4j
    driver = None
    try:
        driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD))
        with driver.session() as session:
            session.run('MATCH (n) DETACH DELETE n')
        logger.info("Neo4j database wiped.")
    except Exception as e:
        logger.error(f"Error wiping Neo4j: {e}")
    finally:
        if driver:
            driver.close()
