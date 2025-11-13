#!/usr/bin/env python3
"""
Script to import trips data from trips.txt file into the trips table.

This script reads the CSV data from trips.txt and imports it into the database
trips table with proper data validation and error handling.
"""

import csv
import os
from sqlalchemy import text
from ..database import database_session_manager

def import_trips_data():
    """
    Import trips data from trips.txt file into the trips table.

    Reads CSV data and performs bulk insert with proper validation
    and timestamp handling.
    """
    print("Starting trips data import...")

    # Get the file path relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    trips_file_path = os.path.join(project_root, "trips.txt")

    if not os.path.exists(trips_file_path):
        print(f"Error: trips.txt file not found at {trips_file_path}")
        print("Please ensure trips.txt is in the project root directory.")
        return

    try:
        with database_session_manager.engine.begin() as conn:
            # Check if trips table exists
            table_exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'trips'
                )
            """)).scalar()

            if not table_exists:
                print("Error: trips table does not exist. Please run migrations first.")
                return

            # Check if trips table has data
            result = conn.execute(text("SELECT COUNT(*) FROM trips")).scalar()

            if result > 0:
                print(f"Warning: Trips table already contains {result} records.")
                response = input("Do you want to clear existing data and reimport? (y/N): ")
                if response.lower() == 'y':
                    print("Clearing existing trips data...")
                    conn.execute(text("DELETE FROM trips"))
                    print("Existing trips data cleared.")
                else:
                    print("Import cancelled.")
                    return

            # Read and import the CSV data
            print(f"Reading trips data from {trips_file_path}...")

            with open(trips_file_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                trips_data = []

                for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is header
                    try:
                        # Validate and prepare data
                        trip_data = {
                            'route_id': row['route_id'].strip() if row['route_id'] else None,
                            'service_id': row['service_id'].strip() if row['service_id'] else None,
                            'trip_id': row['trip_id'].strip() if row['trip_id'] else None,
                            'trip_headsign': row['trip_headsign'].strip() if row['trip_headsign'] else None,
                            'direction_id': int(row['direction_id']) if row['direction_id'].strip() else None,
                            'shape_id': row['shape_id'].strip() if row['shape_id'] else None
                        }

                        # Validate required fields
                        if not trip_data['trip_id']:
                            print(f"Warning: Skipping row {row_num} - missing trip_id")
                            continue

                        trips_data.append(trip_data)

                    except ValueError as e:
                        print(f"Warning: Skipping row {row_num} - invalid data: {e}")
                        continue
                    except KeyError as e:
                        print(f"Error: Missing column {e} in CSV file")
                        return

                if not trips_data:
                    print("No valid data found in trips.txt file")
                    return

                print(f"Found {len(trips_data)} valid trips to import...")

                # Bulk insert using SQLAlchemy text
                conn.execute(
                    text("""
                        INSERT INTO trips (route_id, service_id, trip_id, trip_headsign, direction_id, shape_id, created_at, updated_at)
                        VALUES (:route_id, :service_id, :trip_id, :trip_headsign, :direction_id, :shape_id, NOW(), NOW())
                    """),
                    trips_data
                )

                print(f"Successfully imported {len(trips_data)} trips!")

                # Show some statistics
                total_routes = conn.execute(text("SELECT COUNT(DISTINCT route_id) FROM trips")).scalar()
                total_services = conn.execute(text("SELECT COUNT(DISTINCT service_id) FROM trips")).scalar()
                total_directions = conn.execute(text("SELECT COUNT(DISTINCT direction_id) FROM trips WHERE direction_id IS NOT NULL")).scalar()
                total_shapes = conn.execute(text("SELECT COUNT(DISTINCT shape_id) FROM trips WHERE shape_id IS NOT NULL")).scalar()

                print("\n--- Import Statistics ---")
                print(f"Total trips imported: {len(trips_data)}")
                print(f"Unique routes: {total_routes}")
                print(f"Unique services: {total_services}")
                print(f"Unique directions: {total_directions}")
                print(f"Unique shapes: {total_shapes}")

                # Show sample data
                sample_data = conn.execute(text("""
                    SELECT route_id, trip_headsign, direction_id
                    FROM trips
                    LIMIT 5
                """)).fetchall()

                print("\n--- Sample imported data ---")
                for row in sample_data:
                    print(f"Route: {row.route_id}, Destination: {row.trip_headsign}, Direction: {row.direction_id}")

    except FileNotFoundError:
        print(f"Error: Could not find trips.txt file at {trips_file_path}")
    except Exception as e:
        print(f"Error importing trips data: {e}")
        raise

def main():
    """Main function to run the trips import script."""
    try:
        import_trips_data()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Script failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
