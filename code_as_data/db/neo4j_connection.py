import os
from neo4j import GraphDatabase, exceptions
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "secret123")

class Neo4jConnection:
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            try:
                cls._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                cls._driver.verify_connectivity()
                print(f"Successfully connected to Neo4j at {NEO4J_URI}")
            except exceptions.ServiceUnavailable as e:
                print(f"Error connecting to Neo4j: {e}")
                print(f"Please ensure Neo4j is running at {NEO4J_URI} and credentials are correct.")
                print("Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD environment variables if needed.")
                cls._driver = None # Ensure driver remains None if connection fails
            except exceptions.AuthError as e:
                print(f"Authentication error connecting to Neo4j: {e}")
                print(f"Please check NEO4J_USER and NEO4J_PASSWORD.")
                cls._driver = None
            except Exception as e:
                print(f"An unexpected error occurred while connecting to Neo4j: {e}")
                cls._driver = None
        return cls._driver

    @classmethod
    def close_driver(cls):
        if cls._driver is not None:
            cls._driver.close()
            cls._driver = None
            print("Neo4j connection closed.")

    @classmethod
    def execute_query(cls, query, parameters=None, database=None):
        driver = cls.get_driver()
        if driver is None:
            print("Cannot execute query, driver not available.")
            return [] # Return empty list or raise exception

        records = []
        summary = None
        try:
            with driver.session(database=database) as session:
                result = session.run(query, parameters)
                records = [record for record in result]
                summary = result.consume()
        except exceptions.ServiceUnavailable:
            print(f"Neo4j service unavailable. Could not execute query: {query[:100]}...")
            # Optionally re-raise or handle as per application needs
            cls._driver = None # Reset driver to force re-connection on next attempt
            return [] 
        except Exception as e:
            print(f"Error executing query: {e}")
            print(f"Query: {query}")
            if parameters:
                print(f"Parameters: {parameters}")
            # Optionally re-raise
            return [] # Or raise specific error
        
        # print(f"Query executed: {summary.query}")
        # print(f"Counters: {summary.counters}")
        return records

