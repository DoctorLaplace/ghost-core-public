# In agent/db/graph_db.py

import logging
from typing import List, Dict, Any

from neo4j import GraphDatabase, exceptions

import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GraphDB:
    """
    Handles interactions with the Neo4j graph database for storing and retrieving structured knowledge.
    """

    def __init__(self):
        """
        Initializes the GraphDB driver by connecting to the Neo4j database.
        """
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            logger.info(f"Successfully connected to Neo4j at {config.NEO4J_URI}")
        except exceptions.AuthError as e:
            logger.error(f"Neo4j authentication failed. Check your credentials in .env: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j or verify connectivity: {e}")
            raise

    def close(self):
        """Closes the database connection driver."""
        if self.driver is not None:
            self.driver.close()
            logger.info("Neo4j connection closed.")

    def query(self, cypher_query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Executes a Cypher query against the database.

        Args:
            cypher_query (str): The Cypher query to execute.
            params (Dict[str, Any], optional): Parameters to pass to the query. Defaults to None.

        Returns:
            List[Dict[str, Any]]: A list of records returned by the query.
        """
        params = params or {}
        with self.driver.session() as session:
            try:
                result = session.run(cypher_query, params)
                return [record.data() for record in result]
            except exceptions.CypherSyntaxError as e:
                logger.error(f"Cypher syntax error in query:\n{cypher_query}\nParams: {params}\nError: {e}")
                return []
            except Exception as e:
                logger.error(f"An error occurred executing query: {e}")
                return []

    def add_node_if_not_exists(self, label: str, properties: Dict[str, Any], primary_key: str = 'name'):
        """
        Creates a new node in the graph if a node with the same primary key doesn't already exist.

        Args:
            label (str): The label for the node (e.g., 'Concept', 'Entity').
            properties (Dict[str, Any]): The properties of the node. Must include the primary_key.
            primary_key (str): The property name to use for checking existence (e.g., 'name', 'id').
        """
        if primary_key not in properties:
            logger.error(f"Primary key '{primary_key}' not found in properties for node with label '{label}'.")
            return

        # MERGE is a Cypher command that creates if not exists.
        cypher = f"""
        MERGE (n:{label} {{{primary_key}: $primary_key_value}})
        ON CREATE SET n += $props
        """
        params = {
            "primary_key_value": properties[primary_key],
            "props": properties
        }
        self.query(cypher, params)
        logger.info(f"Merged node '{label}' with {primary_key} '{properties[primary_key]}'")

    def add_relationship_if_not_exists(self, start_node_label: str, start_node_pk: str, start_node_pv: Any,
                                       end_node_label: str, end_node_pk: str, end_node_pv: Any,
                                       relationship_type: str, rel_properties: Dict[str, Any] = None):
        """
        Creates a relationship between two existing nodes if it doesn't already exist.

        Args:
            start_node_label (str): The label of the starting node.
            start_node_pk (str): The primary key property of the starting node.
            start_node_pv (Any): The primary key value of the starting node.
            end_node_label (str): The label of the ending node.
            end_node_pk (str): The primary key property of the ending node.
            end_node_pv (Any): The primary key value of the ending node.
            relationship_type (str): The type of the relationship (e.g., 'IS_A', 'CONTAINS').
            rel_properties (Dict[str, Any], optional): Properties for the relationship.
        """
        rel_properties = rel_properties or {}
        
        # Using MATCH to find the nodes, and MERGE to create the relationship.
        cypher = f"""
        MATCH (a:{start_node_label} {{{start_node_pk}: $start_pv}}), (b:{end_node_label} {{{end_node_pk}: $end_pv}})
        MERGE (a)-[r:{relationship_type}]->(b)
        ON CREATE SET r += $rel_props
        """
        params = {
            "start_pv": start_node_pv,
            "end_pv": end_node_pv,
            "rel_props": rel_properties
        }
        self.query(cypher, params)
        logger.info(f"Merged relationship '{relationship_type}' between '{start_node_pv}' and '{end_node_pv}'")

    def add_entity_edge(self, memory_id: str, entity: str, relation: str) -> None:
        """
        Creates a Memory node and an Entity node, and draws a relation edge between them.
        """
        self.add_node_if_not_exists("Memory", {"id": memory_id}, primary_key="id")
        self.add_node_if_not_exists("Entity", {"name": entity}, primary_key="name")
        self.add_relationship_if_not_exists(
            "Memory", "id", memory_id,
            "Entity", "name", entity,
            relation.upper()
        )

    def get_neighbors(self, entity: str, limit: int = 20) -> list[dict]:
        """
        Retrieves all memory nodes connected to the given entity.
        Returns a list of dicts: [{"memory_id": str, "entity": str, "relation": str}]
        """
        cypher = """
        MATCH (m:Memory)-[r]-(e:Entity {name: $entity})
        RETURN m.id AS memory_id, e.name AS entity, type(r) AS relation
        LIMIT $limit
        """
        params = {"entity": entity, "limit": limit}
        res = self.query(cypher, params)
        output = []
        for r in res:
            output.append({
                "memory_id": r.get("memory_id"),
                "entity": r.get("entity"),
                "relation": r.get("relation")
            })
        return output

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running GraphDB standalone test...")
    try:
        gdb = GraphDB()

        # Clean up database for a fresh test run
        print("\n--- Cleaning up previous test data ---")
        gdb.query("MATCH (n) DETACH DELETE n")

        # Test adding nodes
        print("\n--- Adding Nodes ---")
        gdb.add_node_if_not_exists("Concept", {"name": "Photosynthesis", "category": "Biology"})
        gdb.add_node_if_not_exists("Concept", {"name": "Plant", "category": "Organism"})
        gdb.add_node_if_not_exists("Concept", {"name": "Energy", "category": "Physics"})

        # Test adding relationships
        print("\n--- Adding Relationships ---")
        gdb.add_relationship_if_not_exists("Concept", "name", "Plant", "Concept", "name", "Photosynthesis", "PERFORMS")
        gdb.add_relationship_if_not_exists("Concept", "name", "Photosynthesis", "Concept", "name", "Energy", "PRODUCES", {"type": "chemical"})

        # Test querying the graph
        print("\n--- Querying for relationships ---")
        results = gdb.query("MATCH (a)-[r]->(b) RETURN a.name, type(r), b.name")
        for record in results:
            print(f"{record['a.name']} -[{record['type(r)']}]-> {record['b.name']}")

        gdb.close()
        print("\nStandalone test completed successfully.")

    except Exception as e:
        print(f"An error occurred during the standalone test: {e}")