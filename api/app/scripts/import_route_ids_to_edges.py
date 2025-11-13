#!/usr/bin/env python3
"""
Script to update the edges table with route_id values based on stop_times and trips.
"""

import os
from sqlalchemy import text
from ..database import database_session_manager

def update_edges_with_route_ids():
    print("Starting route_id update for edges...")

    try:
        with database_session_manager.engine.begin() as conn:

            # Check if required tables exist
            required_tables = ["edges", "stop_times", "trips"]
            for table in required_tables:
                exists = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = '{table}'
                    )
                """)).scalar()
                if not exists:
                    print(f"❌ Error: Required table '{table}' does not exist!")
                    return

            # Check if route_id column exists in edges
            col_exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='edges'
                    AND column_name='route_id'
                )
            """)).scalar()

            if not col_exists:
                print("Adding route_id column to edges table...")
                conn.execute(text("ALTER TABLE edges ADD COLUMN route_id VARCHAR"))
                print("✅ route_id column added.")

            print("\nUpdating edges with route_id values... This may take a moment...")

            updated_count = conn.execute(text("""
                UPDATE edges e
                SET route_id = t.route_id
                FROM stop_times st1
                JOIN stop_times st2
                  ON st1.trip_id = st2.trip_id
                 AND st2.stop_sequence = st1.stop_sequence + 1
                JOIN trips t
                  ON st1.trip_id = t.trip_id
                WHERE e.source = st1.stop_id
                  AND e.target = st2.stop_id
            """)).rowcount

            print(f"✅ Successfully updated {updated_count} edges with route_id!")

            # Show some sample updated rows
            sample = conn.execute(text("""
                SELECT id, source, target, route_id
                FROM edges
                WHERE route_id IS NOT NULL
                LIMIT 10
            """)).fetchall()

            print("\nSample updated edges:")
            for row in sample:
                print(f"{row.id}: {row.source} → {row.target} (Route {row.route_id})")

    except Exception as e:
        print(f"❌ Error updating edges: {e}")
        raise

def main():
    try:
        update_edges_with_route_ids()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Script failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
