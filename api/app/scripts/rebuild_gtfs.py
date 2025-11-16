#!/usr/bin/env python3
"""
Build edges directly from GTFS files for optimal Nairobi matatu routing.
Reads raw GTFS files and creates intelligent route network.
"""

import sys
import os
import csv
import logging
from collections import defaultdict, namedtuple
from sqlalchemy import text

# Fix import path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from api.app.database import database_session_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gtfs_edges_builder")

# GTFS data structures
Route = namedtuple('Route', ['route_id', 'route_short_name', 'route_long_name', 'route_type'])
Trip = namedtuple('Trip', ['route_id', 'service_id', 'trip_id', 'trip_headsign', 'direction_id', 'shape_id'])
StopTime = namedtuple('StopTime', ['trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence'])
Frequency = namedtuple('Frequency', ['trip_id', 'start_time', 'end_time', 'headway_secs'])
Stop = namedtuple('Stop', ['stop_id', 'stop_name', 'stop_lat', 'stop_lon'])

class GTFSEdgeBuilder:
    def __init__(self, gtfs_path="/home/murage/Desktop/school/matatus/Mobile_BE/GTFS_FEED_2019"):
        self.gtfs_path = gtfs_path
        self.routes = {}
        self.trips = {}
        self.stop_times = defaultdict(list)
        self.frequencies = defaultdict(list)
        self.stops = {}

    def run(self):
        """Main execution method"""
        log.info("Starting GTFS-based edge building...")

        # 1. Load GTFS data
        self._load_gtfs_data()

        # 2. Build edges using database
        self._build_edges_to_database()

        log.info("GTFS edge building complete!")

    def _load_gtfs_data(self):
        """Load all GTFS files into memory"""
        log.info("Loading GTFS data files...")

        # Load routes.txt
        routes_file = os.path.join(self.gtfs_path, "routes.txt")
        if os.path.exists(routes_file):
            with open(routes_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    route = Route(
                        route_id=row['route_id'],
                        route_short_name=row.get('route_short_name', ''),
                        route_long_name=row.get('route_long_name', ''),
                        route_type=row.get('route_type', '3')  # 3 = bus
                    )
                    self.routes[route.route_id] = route
            log.info(f"Loaded {len(self.routes):,} routes")

        # Load trips.txt
        trips_file = os.path.join(self.gtfs_path, "trips.txt")
        with open(trips_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip = Trip(
                    route_id=row['route_id'],
                    service_id=row['service_id'],
                    trip_id=row['trip_id'],
                    trip_headsign=row.get('trip_headsign', ''),
                    direction_id=int(row.get('direction_id', 0)),
                    shape_id=row.get('shape_id', '')
                )
                self.trips[trip.trip_id] = trip
        log.info(f"Loaded {len(self.trips):,} trips")

        # Load stop_times.txt
        stop_times_file = os.path.join(self.gtfs_path, "stop_times.txt")
        with open(stop_times_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stop_time = StopTime(
                    trip_id=row['trip_id'],
                    arrival_time=row.get('arrival_time', ''),
                    departure_time=row.get('departure_time', ''),
                    stop_id=row['stop_id'],
                    stop_sequence=int(row['stop_sequence'])
                )
                self.stop_times[stop_time.trip_id].append(stop_time)

        # Sort stop_times by sequence for each trip
        for trip_id in self.stop_times:
            self.stop_times[trip_id].sort(key=lambda x: x.stop_sequence)

        log.info(f"Loaded stop_times for {len(self.stop_times):,} trips")

        # Load frequencies.txt
        frequencies_file = os.path.join(self.gtfs_path, "frequencies.txt")
        if os.path.exists(frequencies_file):
            with open(frequencies_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    frequency = Frequency(
                        trip_id=row['trip_id'],
                        start_time=row['start_time'],
                        end_time=row['end_time'],
                        headway_secs=int(row['headway_secs'])
                    )
                    self.frequencies[frequency.trip_id].append(frequency)
            log.info(f"Loaded frequencies for {len(self.frequencies):,} trips")

        # Load stops.txt
        stops_file = os.path.join(self.gtfs_path, "stops.txt")
        if os.path.exists(stops_file):
            with open(stops_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    stop = Stop(
                        stop_id=row['stop_id'],
                        stop_name=row['stop_name'],
                        stop_lat=float(row['stop_lat']),
                        stop_lon=float(row['stop_lon'])
                    )
                    self.stops[stop.stop_id] = stop
            log.info(f"Loaded {len(self.stops):,} stops")

    def _calculate_frequency_score(self, trip_id):
        """Calculate frequency score for a trip"""
        if trip_id not in self.frequencies:
            return 0.5  # Default medium frequency

        frequencies = self.frequencies[trip_id]
        total_score = 0
        total_duration = 0

        for freq in frequencies:
            # Convert time to minutes for duration calculation
            start_mins = self._time_to_minutes(freq.start_time)
            end_mins = self._time_to_minutes(freq.end_time)
            duration = end_mins - start_mins

            # Score based on headway (lower headway = higher score)
            if freq.headway_secs <= 300:  # 5 minutes
                score = 1.0  # High frequency
            elif freq.headway_secs <= 600:  # 10 minutes
                score = 0.8  # Good frequency
            elif freq.headway_secs <= 900:  # 15 minutes
                score = 0.6  # Medium frequency
            else:
                score = 0.3  # Low frequency

            total_score += score * duration
            total_duration += duration

        return total_score / total_duration if total_duration > 0 else 0.5

    def _time_to_minutes(self, time_str):
        """Convert HH:MM:SS to minutes since midnight"""
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            return hours * 60 + minutes
        except:
            return 0

    def _get_route_variant(self, route_id):
        """Extract route variant (A, B, C, etc.) from route_id"""
        import re
        match = re.search(r'([A-Z])(\d*)$', route_id)
        return match.group(1) if match else 'main'

    def _build_edges_to_database(self):
        """Build edges and insert into database"""
        engine = database_session_manager.engine

        with engine.begin() as conn:
            # Backup existing edges
            self._backup_edges(conn)

            # Create new edges table
            self._create_edges_table(conn)

            # Build route edges from GTFS data
            self._insert_route_edges(conn)

            # Add transfer edges
            self._insert_transfer_edges(conn)

            # Add walking edges (limited)
            self._insert_walking_edges(conn)

            # Optimize table
            self._optimize_edges_table(conn)

    def _backup_edges(self, conn):
        """Backup existing edges table"""
        log.info("Backing up existing edges...")
        if conn.execute(text("SELECT to_regclass('edges')")).scalar():
            conn.execute(text("DROP TABLE IF EXISTS edges_old CASCADE"))
            conn.execute(text("ALTER TABLE edges RENAME TO edges_old"))

    def _create_edges_table(self, conn):
        """Create enhanced edges table"""
        log.info("Creating enhanced edges table...")

        conn.execute(text("""
            CREATE TABLE edges (
                id BIGSERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,

                -- Routing costs
                cost DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                reverse_cost DOUBLE PRECISION NOT NULL DEFAULT 1.0,

                -- GTFS attributes
                route_id TEXT,
                trip_id TEXT,
                direction_id INTEGER,
                stop_sequence INTEGER,
                hop_count INTEGER DEFAULT 1,

                -- Enhanced attributes
                edge_type VARCHAR(20) DEFAULT 'direct',
                service_frequency DOUBLE PRECISION DEFAULT 0.5,
                route_variant VARCHAR(10) DEFAULT 'main',
                peak_service BOOLEAN DEFAULT false,
                reliability_score DOUBLE PRECISION DEFAULT 1.0,

                -- Metadata
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),

                -- Constraints
                CONSTRAINT edges_source_target_check CHECK (source != target OR edge_type = 'transfer')
            );
        """))

    def _insert_route_edges(self, conn):
        """Insert route edges from GTFS data"""
        log.info("Building route edges from GTFS data...")

        edges_data = []
        processed_trips = 0

        for trip_id, stop_times in self.stop_times.items():
            if trip_id not in self.trips:
                continue

            trip = self.trips[trip_id]
            frequency_score = self._calculate_frequency_score(trip_id)
            route_variant = self._get_route_variant(trip.route_id)

            # Check if this is peak service (any frequency <= 5 minutes)
            peak_service = any(
                freq.headway_secs <= 300
                for freq in self.frequencies.get(trip_id, [])
            )

            # Create edges between consecutive stops and multi-hop edges
            max_hops = 6  # Allow up to 6 hops for more connectivity
            for i in range(len(stop_times)):
                for j in range(i + 1, min(i + max_hops + 1, len(stop_times))):
                    source_stop = stop_times[i]
                    target_stop = stop_times[j]

                    # Skip if we don't have stop coordinates
                    if (source_stop.stop_id not in self.stops or
                        target_stop.stop_id not in self.stops):
                        continue

                    source_coords = self.stops[source_stop.stop_id]
                    target_coords = self.stops[target_stop.stop_id]

                    # Calculate distance
                    distance = self._calculate_distance(
                        source_coords.stop_lat, source_coords.stop_lon,
                        target_coords.stop_lat, target_coords.stop_lon
                    )

                    hop_count = target_stop.stop_sequence - source_stop.stop_sequence

                    # Distance-based filtering to prevent unrealistic shortcuts
                    max_distance_per_hop = 1500  # Max 1.5km per hop for reasonable connectivity
                    if distance > (hop_count * max_distance_per_hop):
                        continue  # Skip edges that are too long for hop count

                    # Route-based filtering for multi-hop edges
                    if not self._should_create_multi_hop_edge(hop_count, distance, trip.route_id):
                        continue

                    # Calculate cost with frequency weighting and distance penalties
                    if hop_count == 1:
                        # Direct connection
                        base_cost = max(15, min(120, distance / 10))
                        cost = base_cost / max(frequency_score, 0.1)
                    else:
                        # Multi-hop connection with higher distance penalty
                        distance_penalty = max(0, (hop_count - 1) * 15)
                        base_cost = max(25, min(250, 25 + distance_penalty + distance / 20))
                        cost = base_cost / max(frequency_score, 0.1)

                    edge_type = 'direct' if hop_count == 1 else 'multi_hop'

                    # Forward edge
                    edges_data.append({
                        'source': source_stop.stop_id,
                        'target': target_stop.stop_id,
                        'cost': cost,
                        'reverse_cost': cost,
                        'route_id': trip.route_id,
                        'trip_id': trip_id,
                        'direction_id': trip.direction_id,
                        'stop_sequence': target_stop.stop_sequence,
                        'hop_count': hop_count,
                        'edge_type': edge_type,
                        'service_frequency': frequency_score,
                        'route_variant': route_variant,
                        'peak_service': peak_service,
                        'reliability_score': frequency_score
                    })

                    # Bidirectional: Add reverse edge
                    edges_data.append({
                        'source': target_stop.stop_id,
                        'target': source_stop.stop_id,
                        'cost': cost,
                        'reverse_cost': cost,
                        'route_id': trip.route_id,
                        'trip_id': trip_id,
                        'direction_id': trip.direction_id,
                        'stop_sequence': source_stop.stop_sequence,
                        'hop_count': hop_count,
                        'edge_type': edge_type,
                        'service_frequency': frequency_score,
                        'route_variant': route_variant,
                        'peak_service': peak_service,
                        'reliability_score': frequency_score
                    })

            processed_trips += 1
            if processed_trips % 100 == 0:
                log.info(f"Processed {processed_trips} trips...")

        # Batch insert edges
        log.info(f"Inserting {len(edges_data):,} route edges...")

        # First, get node_ids for all stops from stages table
        self._map_stops_to_nodes(conn, edges_data)

        # Insert edges in batches
        batch_size = 1000
        for i in range(0, len(edges_data), batch_size):
            batch = edges_data[i:i + batch_size]

            values = []
            params = {}
            for idx, edge in enumerate(batch):
                if 'source_id' not in edge or 'target_id' not in edge:
                    continue  # Skip edges without node mapping

                param_base = f"edge_{i}_{idx}"
                values.append(f"""(
                    :{param_base}_source, :{param_base}_target,
                    :{param_base}_source_id, :{param_base}_target_id,
                    :{param_base}_cost, :{param_base}_reverse_cost,
                    :{param_base}_route_id, :{param_base}_trip_id,
                    :{param_base}_direction_id, :{param_base}_stop_sequence,
                    :{param_base}_hop_count, :{param_base}_edge_type,
                    :{param_base}_service_frequency, :{param_base}_route_variant,
                    :{param_base}_peak_service, :{param_base}_reliability_score,
                    NOW(), NOW()
                )""")

                # Add parameters
                for key, value in edge.items():
                    params[f"{param_base}_{key}"] = value

            if values:
                insert_sql = f"""
                    INSERT INTO edges (
                        source, target, source_id, target_id,
                        cost, reverse_cost, route_id, trip_id,
                        direction_id, stop_sequence, hop_count, edge_type,
                        service_frequency, route_variant, peak_service, reliability_score,
                        created_at, updated_at
                    ) VALUES {', '.join(values)}
                """

                conn.execute(text(insert_sql), params)

        log.info(f"Inserted {len(edges_data):,} route edges")

    def _map_stops_to_nodes(self, conn, edges_data):
        """Map GTFS stop_ids to database node_ids"""
        log.info("Mapping stops to database nodes...")

        # Get all unique stop_ids
        stop_ids = set()
        for edge in edges_data:
            stop_ids.add(edge['source'])
            stop_ids.add(edge['target'])

        # Query database for stop to node mapping
        if stop_ids:
            stop_ids_list = list(stop_ids)
            placeholders = ','.join([f':stop_{i}' for i in range(len(stop_ids_list))])
            params = {f'stop_{i}': stop_id for i, stop_id in enumerate(stop_ids_list)}
            mapping_sql = f"""
                SELECT stop_id, node_id
                FROM stages
                WHERE stop_id IN ({placeholders})
            """

            stop_to_node = {}
            for row in conn.execute(text(mapping_sql), params).fetchall():
                stop_to_node[row._mapping['stop_id']] = row._mapping['node_id']

            log.info(f"Mapped {len(stop_to_node)} stops to nodes")

            # Add node_ids to edges_data
            for edge in edges_data:
                source_id = stop_to_node.get(edge['source'])
                target_id = stop_to_node.get(edge['target'])

                if source_id and target_id:
                    edge['source_id'] = source_id
                    edge['target_id'] = target_id

    def _should_create_multi_hop_edge(self, hop_count, distance, route_id):
        """Decide whether to create a multi-hop edge based on route characteristics"""
        # Direct hops: always allow
        if hop_count == 1:
            return True

        # Express routes: allow more multi-hop edges for better connectivity
        express_routes = ['23', '24', '46', '56', '111']
        if any(er in route_id for er in express_routes):
            return hop_count <= 4 and distance <= 5000  # Max 4 hops, 5km for express routes

        # Local routes: generous multi-hop edges for maximum connectivity
        return hop_count <= 6 and distance <= 8000  # Max 6 hops, 8km for local routes

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in meters"""
        import math

        # Haversine formula
        R = 6371000  # Earth's radius in meters

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (math.sin(dlat/2) * math.sin(dlat/2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(dlon/2) * math.sin(dlon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    def _insert_transfer_edges(self, conn):
        """Insert intelligent transfer edges"""
        log.info("Adding transfer edges...")

        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, edge_type, reliability_score,
                created_at, updated_at
            )
            SELECT DISTINCT
                s1.stop_id AS source,
                s1.stop_id AS target,
                s1.node_id AS source_id,
                s1.node_id AS target_id,

                -- Smart transfer penalty
                CASE
                    WHEN route_count >= 5 THEN 8.0   -- Major hub
                    WHEN route_count >= 3 THEN 12.0  -- Medium hub
                    ELSE 18.0                        -- Minor stop
                END AS cost,

                CASE
                    WHEN route_count >= 5 THEN 8.0
                    WHEN route_count >= 3 THEN 12.0
                    ELSE 18.0
                END AS reverse_cost,

                'transfer' AS edge_type,
                LEAST(1.0, route_count / 10.0) AS reliability_score,
                NOW(), NOW()

            FROM (
                SELECT
                    s.stop_id,
                    s.node_id,
                    COUNT(DISTINCT e.route_id) as route_count
                FROM stages s
                JOIN edges e ON (s.stop_id = e.source OR s.stop_id = e.target)
                WHERE e.route_id IS NOT NULL
                GROUP BY s.stop_id, s.node_id
                HAVING COUNT(DISTINCT e.route_id) > 1
            ) s1
        """))

    def _insert_walking_edges(self, conn):
        """Insert CBD-aware walking connections"""
        log.info("Adding CBD-aware walking edges...")

        conn.execute(text("""
            INSERT INTO edges (
                source, target, source_id, target_id,
                cost, reverse_cost, edge_type, reliability_score,
                created_at, updated_at
            )
            SELECT DISTINCT
                walking_candidates.stop_id AS source,
                walking_candidates.target_stop AS target,
                walking_candidates.node_id AS source_id,
                walking_candidates.target_node AS target_id,

                -- CBD walking is cheaper/faster (100m/min vs 80m/min outside CBD)
                CASE
                    WHEN walking_candidates.is_cbd THEN (distance_m / 100.0) + 10.0  -- Faster CBD walking
                    ELSE (distance_m / 80.0) + 30.0  -- Normal walking penalty
                END AS cost,

                CASE
                    WHEN walking_candidates.is_cbd THEN (distance_m / 100.0) + 10.0
                    ELSE (distance_m / 80.0) + 30.0
                END AS reverse_cost,

                'walking' AS edge_type,
                CASE WHEN walking_candidates.is_cbd THEN 0.9 ELSE 0.6 END AS reliability_score,
                NOW(), NOW()

            FROM (
                SELECT DISTINCT
                    s1.stop_id, s1.node_id, s1.stop_lat, s1.stop_lon,
                    s2.stop_id as target_stop, s2.node_id as target_node,
                    ST_DistanceSphere(
                        ST_MakePoint(s1.stop_lon, s1.stop_lat),
                        ST_MakePoint(s2.stop_lon, s2.stop_lat)
                    ) as distance_m,
                    -- CBD detection (within 2km of city center: -1.286, 36.817)
                    (ST_DistanceSphere(ST_MakePoint(s1.stop_lon, s1.stop_lat), ST_MakePoint(36.817, -1.286)) <= 2000
                     AND ST_DistanceSphere(ST_MakePoint(s2.stop_lon, s2.stop_lat), ST_MakePoint(36.817, -1.286)) <= 2000) as is_cbd
                FROM stages s1, stages s2
                WHERE s1.stop_id != s2.stop_id
                AND ST_DistanceSphere(
                    ST_MakePoint(s1.stop_lon, s1.stop_lat),
                    ST_MakePoint(s2.stop_lon, s2.stop_lat)
                ) BETWEEN 100 AND 600  -- Allow up to 600m for CBD walking
            ) walking_candidates
            WHERE
                -- Allow CBD walking freely to enable better matatu connections
                (walking_candidates.is_cbd) OR
                -- Outside CBD, only walk between different route networks to avoid redundancy
                (NOT EXISTS (
                    SELECT 1 FROM edges e
                    WHERE ((e.source = walking_candidates.stop_id AND e.target = walking_candidates.target_stop)
                        OR (e.source = walking_candidates.target_stop AND e.target = walking_candidates.stop_id))
                    AND e.edge_type != 'walking'
                    AND e.route_id IS NOT NULL
                ))
            LIMIT 10000  -- Increased limit for CBD walking connections
        """))

    def _optimize_edges_table(self, conn):
        """Optimize edges table with indexes and statistics"""
        log.info("Optimizing edges table...")

        # Remove duplicates
        conn.execute(text("""
            DELETE FROM edges a
            USING (
                SELECT MIN(ctid) as keep_ctid,
                       source_id, target_id, route_id, direction_id, hop_count
                FROM edges
                GROUP BY source_id, target_id, route_id, direction_id, hop_count
                HAVING COUNT(*) > 1
            ) d
            WHERE a.source_id = d.source_id
              AND a.target_id = d.target_id
              AND (a.route_id IS NOT DISTINCT FROM d.route_id)
              AND (a.direction_id IS NOT DISTINCT FROM d.direction_id)
              AND a.hop_count = d.hop_count
              AND a.ctid <> d.keep_ctid;
        """))

        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_edges_source_id ON edges(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_target_id ON edges(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_route_id ON edges(route_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_direction ON edges(direction_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type)",
            "CREATE INDEX IF NOT EXISTS idx_edges_frequency ON edges(service_frequency DESC)",
            "CREATE INDEX IF NOT EXISTS idx_edges_cost ON edges(cost)",
            "CREATE INDEX IF NOT EXISTS idx_edges_routing ON edges(source_id, target_id, cost)"
        ]

        for index_sql in indexes:
            conn.execute(text(index_sql))

        conn.execute(text("ANALYZE edges"))

        # Print statistics
        stats = conn.execute(text("""
            SELECT
                COUNT(*) as total_edges,
                COUNT(*) FILTER (WHERE edge_type = 'direct') as direct_edges,
                COUNT(*) FILTER (WHERE edge_type = 'multi_hop') as multi_hop_edges,
                COUNT(*) FILTER (WHERE edge_type = 'transfer') as transfer_edges,
                COUNT(*) FILTER (WHERE edge_type = 'walking') as walking_edges,
                COUNT(DISTINCT route_id) FILTER (WHERE route_id IS NOT NULL) as unique_routes,
                ROUND(AVG(service_frequency) FILTER (WHERE service_frequency > 0)::numeric, 3) as avg_frequency,
                ROUND(AVG(cost)::numeric, 2) as avg_cost
            FROM edges
        """)).fetchone()

        log.info("=== EDGE BUILDING SUMMARY ===")
        log.info(f"Total edges: {stats._mapping['total_edges']:,}")
        log.info(f"  - Direct: {stats._mapping['direct_edges']:,}")
        log.info(f"  - Multi-hop: {stats._mapping['multi_hop_edges']:,}")
        log.info(f"  - Transfer: {stats._mapping['transfer_edges']:,}")
        log.info(f"  - Walking: {stats._mapping['walking_edges']:,}")
        log.info(f"Unique routes: {stats._mapping['unique_routes']:,}")
        log.info(f"Average frequency score: {stats._mapping['avg_frequency']}")
        log.info(f"Average edge cost: {stats._mapping['avg_cost']}")

def run():
    """Main entry point"""
    builder = GTFSEdgeBuilder()
    builder.run()

if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        log.exception("GTFS edge building failed: %s", exc)
        sys.exit(1)
