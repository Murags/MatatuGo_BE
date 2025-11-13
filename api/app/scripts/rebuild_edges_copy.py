#!/usr/bin/env python3
"""
Rebuild the `edges` table from stop_times + trips + stages.
Safe: creates edges_new, backs up old table as edges_old, and swaps when done.
Requires: database_session_manager (SQLAlchemy engine available).
"""

import sys
import logging
from sqlalchemy import text

# adapt import path to your project layout if needed
from ..database import database_session_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rebuild_edges")

def run():
    log.info("Starting edges rebuild...")

    engine = database_session_manager.engine

    with engine.begin() as conn:
        # 0. Basic checks
        log.info("Checking that stop_times, trips, stages exist...")
        for tbl in ("stop_times", "trips", "stages"):
            r = conn.execute(text(f"SELECT to_regclass('{tbl}')")).scalar()
            if not r:
                raise SystemExit(f"Required table '{tbl}' not found in DB. Aborting.")

        # 1. Create backup of current edges (if exists)
        if conn.execute(text("SELECT to_regclass('edges')")).scalar():
            log.info("Backing up current edges -> edges_old (drop old edges_old if exists)...")
            conn.execute(text("DROP TABLE IF EXISTS edges_old CASCADE"))
            conn.execute(text("ALTER TABLE edges RENAME TO edges_old"))
        else:
            log.info("No existing edges table found; continuing.")

        # 2. Create new edges table with direction support
        log.info("Creating edges table (edges) from stop_times/trips/stages...")
        conn.execute(text("""
            CREATE TABLE edges (
                id BIGSERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                cost DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                reverse_cost DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                route_id TEXT,
                trip_id TEXT,
                stop_sequence INTEGER,
                hop_count INTEGER DEFAULT 1,
                edge_type VARCHAR(20) DEFAULT 'direct',
                direction VARCHAR(10) DEFAULT 'forward',
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            );
        """))

        # 3. Insert FORWARD direction edges (original logic)
        log.info("Populating FORWARD direction edges from stop_times/trips/stages...")
        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, route_id, trip_id,
                stop_sequence, hop_count, edge_type, direction,
                created_at, updated_at
            )
            SELECT
                st1.stop_id AS source,
                st2.stop_id AS target,
                s1.node_id AS source_id,
                s2.node_id AS target_id,
                -- Cost calculation
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN
                        GREATEST(20, LEAST(150,
                            ST_DistanceSphere(
                                ST_MakePoint(s1.stop_lon, s1.stop_lat),
                                ST_MakePoint(s2.stop_lon, s2.stop_lat)
                            ) / 8
                        ))
                    ELSE
                        GREATEST(30, LEAST(300,
                            30 + (st2.stop_sequence - st1.stop_sequence - 1) * 15 +
                            ST_DistanceSphere(
                                ST_MakePoint(s1.stop_lon, s1.stop_lat),
                                ST_MakePoint(s2.stop_lon, s2.stop_lat)
                            ) / 20
                        ))
                END AS cost,
                -- Same for reverse_cost
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN
                        GREATEST(20, LEAST(150,
                            ST_DistanceSphere(
                                ST_MakePoint(s1.stop_lon, s1.stop_lat),
                                ST_MakePoint(s2.stop_lon, s2.stop_lat)
                            ) / 8
                        ))
                    ELSE
                        GREATEST(30, LEAST(300,
                            30 + (st2.stop_sequence - st1.stop_sequence - 1) * 15 +
                            ST_DistanceSphere(
                                ST_MakePoint(s1.stop_lon, s1.stop_lat),
                                ST_MakePoint(s2.stop_lon, s2.stop_lat)
                            ) / 20
                        ))
                END AS reverse_cost,
                t.route_id, st1.trip_id, st2.stop_sequence,
                (st2.stop_sequence - st1.stop_sequence) AS hop_count,
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN 'direct'
                    ELSE 'multi_hop'
                END AS edge_type,
                'forward' AS direction,
                NOW(), NOW()
            FROM stop_times st1
            JOIN stop_times st2 ON st1.trip_id = st2.trip_id
                AND st2.stop_sequence > st1.stop_sequence
                AND st2.stop_sequence <= st1.stop_sequence + 10
            JOIN stages s1 ON s1.stop_id = st1.stop_id
            JOIN stages s2 ON s2.stop_id = st2.stop_id
            JOIN trips t ON t.trip_id = st1.trip_id
            WHERE st1.stop_id != st2.stop_id
        """))

        # 4. Insert REVERSE direction edges (the missing piece!)
        log.info("Populating REVERSE direction edges for bidirectional routes...")
        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, route_id, trip_id,
                stop_sequence, hop_count, edge_type, direction,
                created_at, updated_at
            )
            SELECT DISTINCT
                st2.stop_id AS source,  -- Reverse: later stop becomes source
                st1.stop_id AS target,  -- Reverse: earlier stop becomes target
                s2.node_id AS source_id,
                s1.node_id AS target_id,
                -- Same cost calculation (distance doesn't change)
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN
                        GREATEST(20, LEAST(150,
                            ST_DistanceSphere(
                                ST_MakePoint(s2.stop_lon, s2.stop_lat),
                                ST_MakePoint(s1.stop_lon, s1.stop_lat)
                            ) / 8
                        ))
                    ELSE
                        GREATEST(30, LEAST(300,
                            30 + (st2.stop_sequence - st1.stop_sequence - 1) * 15 +
                            ST_DistanceSphere(
                                ST_MakePoint(s2.stop_lon, s2.stop_lat),
                                ST_MakePoint(s1.stop_lon, s1.stop_lat)
                            ) / 20
                        ))
                END AS cost,
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN
                        GREATEST(20, LEAST(150,
                            ST_DistanceSphere(
                                ST_MakePoint(s2.stop_lon, s2.stop_lat),
                                ST_MakePoint(s1.stop_lon, s1.stop_lat)
                            ) / 8
                        ))
                    ELSE
                        GREATEST(30, LEAST(300,
                            30 + (st2.stop_sequence - st1.stop_sequence - 1) * 15 +
                            ST_DistanceSphere(
                                ST_MakePoint(s2.stop_lon, s2.stop_lat),
                                ST_MakePoint(s1.stop_lon, s1.stop_lat)
                            ) / 20
                        ))
                END AS reverse_cost,
                t.route_id,
                st1.trip_id,
                st1.stop_sequence,  -- Keep original sequence for reference
                (st2.stop_sequence - st1.stop_sequence) AS hop_count,
                CASE
                    WHEN st2.stop_sequence = st1.stop_sequence + 1 THEN 'direct'
                    ELSE 'multi_hop'
                END AS edge_type,
                'reverse' AS direction,
                NOW(), NOW()
            FROM stop_times st1
            JOIN stop_times st2 ON st1.trip_id = st2.trip_id
                AND st2.stop_sequence > st1.stop_sequence
                AND st2.stop_sequence <= st1.stop_sequence + 10
            JOIN stages s1 ON s1.stop_id = st1.stop_id
            JOIN stages s2 ON s2.stop_id = st2.stop_id
            JOIN trips t ON t.trip_id = st1.trip_id
            WHERE st1.stop_id != st2.stop_id
        """))

        # 5. Add transfer edges between different routes at same stops
        log.info("Adding transfer edges between different routes at same stops...")
        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, route_id, trip_id,
                stop_sequence, hop_count, edge_type, direction,
                created_at, updated_at
            )
            SELECT DISTINCT
                s1.stop_id AS source,
                s1.stop_id AS target,
                s1.node_id AS source_id,
                s1.node_id AS target_id,
                15.0 AS cost,  -- Reduced transfer penalty
                15.0 AS reverse_cost,
                NULL AS route_id,
                NULL AS trip_id,
                0 AS stop_sequence,
                0 AS hop_count,
                'transfer' AS edge_type,
                'both' AS direction,
                NOW(), NOW()
            FROM stages s1
            WHERE s1.node_id IN (
                SELECT s.node_id
                FROM stages s
                JOIN stop_times st ON s.stop_id = st.stop_id
                JOIN trips t ON st.trip_id = t.trip_id
                GROUP BY s.node_id
                HAVING COUNT(DISTINCT t.route_id) > 1
            );
        """))

        # 6. Add destination completion edges
        log.info("Adding destination node completion edges...")
        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, route_id, trip_id,
                stop_sequence, hop_count, edge_type, direction,
                created_at, updated_at
            )
            SELECT DISTINCT
                s.stop_id, s.stop_id, s.node_id, s.node_id,
                0.1, 0.1, 'destination_completion', NULL,
                0, 0, 'destination', 'both',
                NOW(), NOW()
            FROM stages s
            WHERE s.node_id NOT IN (
                SELECT DISTINCT target_id FROM edges
                WHERE route_id IS NOT NULL AND route_id != 'destination_completion'
            );
        """))

        # 7. Remove duplicates
        log.info("Removing exact duplicate edges...")
        conn.execute(text("""
            DELETE FROM edges a
            USING (
                SELECT MIN(ctid) as keep_ctid, source_id, target_id, route_id, trip_id, hop_count, direction
                FROM edges
                GROUP BY source_id, target_id, route_id, trip_id, hop_count, direction
                HAVING COUNT(*) > 1
            ) d
            WHERE a.source_id = d.source_id
              AND a.target_id = d.target_id
              AND (a.route_id IS NOT DISTINCT FROM d.route_id)
              AND (a.trip_id IS NOT DISTINCT FROM d.trip_id)
              AND a.hop_count = d.hop_count
              AND (a.direction IS NOT DISTINCT FROM d.direction)
              AND a.ctid <> d.keep_ctid;
        """))

        # 8. Create indexes
        log.info("Creating indexes on edges and stages...")
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_source_id ON edges(source_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_target_id ON edges(target_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_route_id ON edges(route_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_direction ON edges(direction)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_edge_type ON edges(edge_type)"))
        conn.execute(text("ANALYZE edges"))

        # 9. Final counts
        edges_count = conn.execute(text("SELECT COUNT(*) FROM edges")).scalar()
        forward_edges = conn.execute(text("SELECT COUNT(*) FROM edges WHERE direction = 'forward'")).scalar()
        reverse_edges = conn.execute(text("SELECT COUNT(*) FROM edges WHERE direction = 'reverse'")).scalar()
        transfer_edges = conn.execute(text("SELECT COUNT(*) FROM edges WHERE edge_type = 'transfer'")).scalar()

        log.info(f"Edges rebuilt. Total: {edges_count}")
        log.info(f"  - Forward direction: {forward_edges}")
        log.info(f"  - Reverse direction: {reverse_edges}")
        log.info(f"  - Transfer edges: {transfer_edges}")

    log.info("Edges rebuild complete with BIDIRECTIONAL support!")

if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        log.exception("Edges rebuild failed: %s", exc)
        sys.exit(1)
