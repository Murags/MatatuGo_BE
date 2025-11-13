#!/usr/bin/env python3
"""
Script to populate the edges table from stop_times data.

This script creates edges between consecutive stops in the same trip,
which can be used for routing and pathfinding algorithms.
"""

from sqlalchemy import text
from ..database import database_session_manager

def populate_edges():
    """
    Populate edges table from stop_times data.

    Creates edges between consecutive stops on the same trip,
    with cost and reverse_cost set to 1 (can be modified later).
    """
    print("Starting to populate edges table...")

    try:
        with database_session_manager.engine.begin() as conn:
            # First, check if we have any stop_times data
            result = conn.execute(text("SELECT COUNT(*) FROM stop_times")).scalar()
            if result == 0:
                print("Warning: No data found in stop_times table. Please ensure stop_times data is loaded first.")
                return

            print(f"Found {result} records in stop_times table")

            # Check if edges table already has data
            edges_count = conn.execute(text("SELECT COUNT(*) FROM edges")).scalar()
            if edges_count > 0:
                print(f"Warning: Edges table already contains {edges_count} records.")
                response = input("Do you want to clear existing edges and repopulate? (y/N): ")
                if response.lower() == 'y':
                    print("Clearing existing edges...")
                    conn.execute(text("DELETE FROM edges"))
                else:
                    print("Skipping population. Exiting.")
                    return

            # Insert edges from consecutive stops
            print("Creating edges from consecutive stops...")
            result = conn.execute(text("""
                INSERT INTO edges (source, target, cost, reverse_cost, created_at, updated_at)
                SELECT
                    st1.stop_id AS source,
                    st2.stop_id AS target,
                    1 AS cost,
                    1 AS reverse_cost,
                    NOW() AS created_at,
                    NOW() AS updated_at
                FROM stop_times st1
                JOIN stop_times st2
                  ON st1.trip_id = st2.trip_id
                 AND st2.stop_sequence = st1.stop_sequence + 1
                ORDER BY st1.trip_id, st1.stop_sequence;
            """))

            # Get the number of inserted rows
            edges_inserted = conn.execute(text("SELECT COUNT(*) FROM edges")).scalar()

            print(f"Successfully populated {edges_inserted} edges from stop_times data")
            print("Edge population completed successfully!")

    except Exception as e:
        print(f"Error populating edges: {e}")
        raise

def main():
    """Main function to run the edge population script."""
    try:
        populate_edges()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Script failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
