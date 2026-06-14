# debug/show_memories.py
# Displays all memories from both Qdrant (vector) and Neo4j (graph) databases.

import os
import sys

# Add the parent directory to sys.path so config can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from qdrant_client import QdrantClient, models
from neo4j import GraphDatabase, exceptions

QDRANT_COLLECTION_NAME = "agent_ltm"

def show_qdrant_memories():
    """Connects to Qdrant and prints all memories in the collection."""
    print('\n' + '='*25 + ' QDRANT MEMORIES ' + '='*25)
    try:
        client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
        print(f'Successfully connected to Qdrant at {config.QDRANT_HOST}:{config.QDRANT_PORT}')

        try:
            count_result = client.count(collection_name=QDRANT_COLLECTION_NAME, exact=True)
            total_vectors = count_result.count
            print(f"Found {total_vectors} memories in collection '{QDRANT_COLLECTION_NAME}'.")

            if total_vectors == 0:
                return

            # Scroll through all points in the collection
            scrolled_points, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                limit=100, # Adjust batch size as needed
                with_payload=True,
                with_vectors=False # Set to True if you want to see the vectors
            )

            point_counter = 0
            while scrolled_points:
                for point in scrolled_points:
                    point_counter += 1
                    print(f'\n--- Memory {point_counter} (ID: {point.id}) ---')
                    print(point.payload)
                
                if next_offset is None:
                    break
                
                scrolled_points, next_offset = client.scroll(
                    collection_name=QDRANT_COLLECTION_NAME,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False
                )

        except Exception as e:
            print(f"Could not retrieve memories from collection '{QDRANT_COLLECTION_NAME}'. It might not exist.")
            print(f'Error details: {e}')

    except Exception as e:
        print(f'An error occurred while connecting to Qdrant: {e}')

def show_neo4j_memories():
    """Connects to Neo4j and prints all nodes and relationships."""
    print('\n' + '='*25 + ' NEO4J MEMORIES ' + '='*26)
    driver = None
    try:
        driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )
        driver.verify_connectivity()
        print(f'Successfully connected to Neo4j at {config.NEO4J_URI}')

        with driver.session() as session:
            # Get all nodes
            nodes_result = session.run("MATCH (n) RETURN n, labels(n) as labels")
            nodes_data = list(nodes_result)
            print(f'\nFound {len(nodes_data)} nodes:')
            if not nodes_data:
                print('  (No nodes in the database)')
            else:
                for i, record in enumerate(nodes_data):
                    node = record["n"]
                    labels = record["labels"]
                    print(f'  {i+1}. Labels: {labels}, Properties: {dict(node.items())}')

            # Get all relationships
            rels_result = session.run("MATCH (a)-[r]->(b) RETURN a.name, type(r) as rel_type, b.name")
            rels_data = list(rels_result)
            print(f'\nFound {len(rels_data)} relationships:')
            if not rels_data:
                print('  (No relationships in the database)')
            else:
                for i, record in enumerate(rels_data):
                    print(f'  {i+1}. ({record["a.name"]}) -[{record["rel_type"]}]-> ({record["b.name"]})')

    except exceptions.AuthError as e:
        print(f'Neo4j authentication failed: {e}')
    except Exception as e:
        print(f'An error occurred while connecting to or querying Neo4j: {e}')
    finally:
        if driver is not None:
            driver.close()

if __name__ == "__main__":
    show_qdrant_memories()
    show_neo4j_memories()
    print('\n' + '='*67)
