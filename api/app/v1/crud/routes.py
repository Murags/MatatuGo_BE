from fastapi import HTTPException
from sqlalchemy import text
from ...database import database_session_manager

async def get_route(origin: str, destination: str, max_alternatives: int = 3):
    """
    Get the best routes between two stops including transfer points.
    Returns up to max_alternatives route options.
    """

    origin = origin.strip()
    destination = destination.strip()
    TRANSFER_PENALTY = 10.0

    with database_session_manager.engine.connect() as conn:

        # Check if pgRouting is available
        try:
            conn.execute(text("SELECT pgr_version()")).fetchone()
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="pgRouting extension not available"
            )

        # Lookup stops by name
        lookup_sql = text("""
            SELECT stop_id, stop_name, node_id
            FROM stages
            WHERE stop_name ILIKE :name
            LIMIT 1
        """)

        origin_row = conn.execute(lookup_sql, {"name": f"%{origin}%"}).fetchone()
        dest_row = conn.execute(lookup_sql, {"name": f"%{destination}%"}).fetchone()

        if not origin_row or not dest_row:
            raise HTTPException(status_code=404, detail="Origin or destination stop not found")

        origin_node = origin_row._mapping["node_id"]
        dest_node = dest_row._mapping["node_id"]

        # Build the pgRouting query string with actual values
        pgrouting_query = f"""
            WITH base AS (
                SELECT id,
                       source_id AS source,
                       target_id AS target,
                       1.0 AS hop_cost,
                       route_id
                FROM edges
                WHERE cost IS NOT NULL
            ),
            penalized AS (
                SELECT id,
                       source,
                       target,
                       CASE
                           WHEN LAG(route_id) OVER (ORDER BY id) = route_id
                                THEN hop_cost
                           ELSE hop_cost + {TRANSFER_PENALTY}
                       END AS cost
                FROM base
            )
            SELECT id, source, target, cost FROM penalized
        """

        # Get multiple alternative paths using pgr_ksp (k-shortest paths)
        routing_sql = text("""
            SELECT p.path_id,
                   p.seq,
                   p.node AS node_id,
                   p.edge,
                   s.stop_name,
                   e.route_id,
                   p.cost AS step_cost,
                   p.agg_cost AS total_cost
            FROM pgr_ksp(
                :query,
                :origin_node,
                :dest_node,
                :k,
                directed := true
            ) AS p
            LEFT JOIN edges e ON p.edge = e.id
            LEFT JOIN stages s ON p.node = s.node_id
            ORDER BY p.path_id, p.seq
        """)

        try:
            rows = conn.execute(routing_sql, {
                "query": pgrouting_query,
                "origin_node": origin_node,
                "dest_node": dest_node,
                "k": max_alternatives
            }).fetchall()
        except Exception as e:
            # Fallback to single path if pgr_ksp fails
            try:
                fallback_sql = text("""
                    SELECT 1 as path_id,
                           p.seq,
                           p.node AS node_id,
                           p.edge,
                           s.stop_name,
                           e.route_id,
                           p.cost AS step_cost,
                           p.agg_cost AS total_cost
                    FROM pgr_dijkstra(
                        :query,
                        :origin_node,
                        :dest_node,
                        directed := true
                    ) AS p
                    LEFT JOIN edges e ON p.edge = e.id
                    LEFT JOIN stages s ON p.node = s.node_id
                    ORDER BY p.seq
                """)
                rows = conn.execute(fallback_sql, {
                    "query": pgrouting_query,
                    "origin_node": origin_node,
                    "dest_node": dest_node
                }).fetchall()
            except Exception as fallback_error:
                raise HTTPException(status_code=500, detail=f"Routing failed: {str(fallback_error)}")

        if not rows:
            raise HTTPException(status_code=404, detail="No route found")

        # Process results into alternative routes
        routes_by_path = {}

        for row in rows:
            path_id = row._mapping.get("path_id", 1)
            route_id = row._mapping.get("route_id")
            stop_name = row._mapping.get("stop_name")
            total_cost = row._mapping.get("total_cost", 0)

            if not stop_name or not route_id:
                continue

            if path_id not in routes_by_path:
                routes_by_path[path_id] = {
                    "segments": [],
                    "current_segment": None,
                    "total_cost": total_cost
                }

            path_data = routes_by_path[path_id]

            if path_data["current_segment"] is None:
                path_data["current_segment"] = {
                    "route_id": route_id,
                    "board": stop_name,
                    "stops": [stop_name]
                }
            else:
                if route_id != path_data["current_segment"]["route_id"]:
                    # Transfer point
                    path_data["current_segment"]["alight"] = path_data["current_segment"]["stops"][-1]
                    path_data["segments"].append(path_data["current_segment"])

                    path_data["current_segment"] = {
                        "route_id": route_id,
                        "board": stop_name,
                        "stops": [stop_name]
                    }
                else:
                    path_data["current_segment"]["stops"].append(stop_name)

        # Close final segments for each path
        for path_data in routes_by_path.values():
            if path_data["current_segment"]:
                path_data["current_segment"]["alight"] = path_data["current_segment"]["stops"][-1]
                path_data["segments"].append(path_data["current_segment"])

        # Get route labels
        all_route_ids = set()
        for path_data in routes_by_path.values():
            for segment in path_data["segments"]:
                if segment["route_id"]:
                    all_route_ids.add(segment["route_id"])

        route_map = {}
        if all_route_ids:
            label_sql = text("""
                SELECT route_id, route_short_name
                FROM routes
                WHERE route_id = ANY(:route_ids)
            """)
            label_rows = conn.execute(label_sql, {"route_ids": list(all_route_ids)}).fetchall()
            for r in label_rows:
                route_map[r._mapping["route_id"]] = r._mapping["route_short_name"]

        # Build final response with alternatives
        alternatives = []
        for path_id in sorted(routes_by_path.keys()):
            path_data = routes_by_path[path_id]

            # Add route labels
            for seg in path_data["segments"]:
                seg["route_label"] = route_map.get(seg["route_id"], seg["route_id"])

            alternatives.append({
                "route_rank": len(alternatives) + 1,
                "total_cost": path_data["total_cost"],
                "transfers": max(0, len(path_data["segments"]) - 1),
                "segments": path_data["segments"],
                "estimated_duration": len([stop for seg in path_data["segments"] for stop in seg["stops"]]) * 2  # rough estimate
            })

        # Sort by quality (fewer transfers, then lower cost)
        alternatives.sort(key=lambda x: (x["transfers"], x["total_cost"]))

        return {
            "origin": origin_row._mapping["stop_name"],
            "destination": dest_row._mapping["stop_name"],
            "alternatives_count": len(alternatives),
            "routes": alternatives[:max_alternatives]
        }

# Also add a convenience function for single best route (backward compatibility)
async def get_best_route(origin: str, destination: str):
    """Get the single best route between two stops."""
    result = await get_route(origin, destination, max_alternatives=1)
    if result["routes"]:
        best_route = result["routes"][0]
        return {
            "origin": result["origin"],
            "destination": result["destination"],
            "transfers": best_route["transfers"],
            "segments": best_route["segments"]
        }
    else:
        raise HTTPException(status_code=404, detail="No route found")


async def get_route_by_coordinates(
    origin_lat: float, origin_lon: float,
    dest_lat: float, dest_lon: float,
    search_radius: int = 500,
    max_candidates: int = 5,
    max_alternatives: int = 3
):
    """
    Find optimal routes between coordinates considering multiple nearby stops.
    Tests combinations and returns multiple route alternatives with least transfers.
    """

    with database_session_manager.engine.connect() as conn:

        # Check if pgRouting is available
        try:
            conn.execute(text("SELECT pgr_version()")).fetchone()
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="pgRouting extension not available"
            )

        # Find candidate stops near origin and destination
        candidate_sql = text("""
            WITH origin_candidates AS (
                SELECT
                    stop_id,
                    stop_name,
                    node_id,
                    stop_lat,
                    stop_lon,
                    ST_DistanceSphere(
                        ST_MakePoint(stop_lon, stop_lat),
                        ST_MakePoint(:origin_lon, :origin_lat)
                    ) AS walk_distance_m
                FROM stages
                WHERE ST_DistanceSphere(
                    ST_MakePoint(stop_lon, stop_lat),
                    ST_MakePoint(:origin_lon, :origin_lat)
                ) <= :search_radius
                ORDER BY walk_distance_m
                LIMIT :max_candidates
            ),
            dest_candidates AS (
                SELECT
                    stop_id,
                    stop_name,
                    node_id,
                    stop_lat,
                    stop_lon,
                    ST_DistanceSphere(
                        ST_MakePoint(stop_lon, stop_lat),
                        ST_MakePoint(:dest_lon, :dest_lat)
                    ) AS walk_distance_m
                FROM stages
                WHERE ST_DistanceSphere(
                    ST_MakePoint(stop_lon, stop_lat),
                    ST_MakePoint(:dest_lon, :dest_lat)
                ) <= :search_radius
                ORDER BY walk_distance_m
                LIMIT :max_candidates
            )
            SELECT
                'origin' as location_type,
                stop_id, stop_name, node_id, stop_lat, stop_lon, walk_distance_m
            FROM origin_candidates
            UNION ALL
            SELECT
                'destination' as location_type,
                stop_id, stop_name, node_id, stop_lat, stop_lon, walk_distance_m
            FROM dest_candidates
            ORDER BY location_type, walk_distance_m
        """)

        candidates = conn.execute(candidate_sql, {
            "origin_lat": origin_lat,
            "origin_lon": origin_lon,
            "dest_lat": dest_lat,
            "dest_lon": dest_lon,
            "search_radius": search_radius,
            "max_candidates": max_candidates
        }).fetchall()

        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No stops found within {search_radius}m of given coordinates"
            )

        # Separate origin and destination candidates
        origin_candidates = [c for c in candidates if c._mapping["location_type"] == "origin"]
        dest_candidates = [c for c in candidates if c._mapping["location_type"] == "destination"]

        if not origin_candidates or not dest_candidates:
            raise HTTPException(
                status_code=404,
                detail="Could not find candidate stops for both origin and destination"
            )

        # Test all combinations to find best routes
        route_options = []
        total_attempts = 0
        successful_routes = 0

        # CBD-favoring routing query that encourages routing through town for cross-corridor journeys
        # Nairobi CBD center coordinates (approx): -1.286, 36.817
        routing_query = """
            WITH cbd_edges AS (
                SELECT e.*, 
                       s1.stop_lat as source_lat, s1.stop_lon as source_lon,
                       s2.stop_lat as target_lat, s2.stop_lon as target_lon,
                       -- Check if either source or target is in CBD (within ~2km radius)
                       CASE WHEN (
                           ST_DistanceSphere(
                               ST_MakePoint(s1.stop_lon, s1.stop_lat),
                               ST_MakePoint(36.817, -1.286)
                           ) <= 2000 
                           OR
                           ST_DistanceSphere(
                               ST_MakePoint(s2.stop_lon, s2.stop_lat),
                               ST_MakePoint(36.817, -1.286)
                           ) <= 2000
                       ) THEN true ELSE false END as is_cbd_edge
                FROM edges e
                JOIN stages s1 ON e.source_id = s1.node_id
                JOIN stages s2 ON e.target_id = s2.node_id
                WHERE e.cost IS NOT NULL AND e.cost > 0
            )
            SELECT id, source_id AS source, target_id AS target, 
                   CASE 
                       -- Strongly favor direct routes
                       WHEN edge_type = 'direct' THEN cost * 0.7
                       
                       -- CBD edges get significant bonus (cheaper routing through town)
                       WHEN is_cbd_edge AND edge_type = 'multi_hop' THEN cost * 0.6
                       WHEN is_cbd_edge AND edge_type = 'transfer' THEN cost * 0.8
                       
                       -- Regular multi-hop routes
                       WHEN edge_type = 'multi_hop' AND hop_count <= 3 THEN cost * 1.0
                       WHEN edge_type = 'multi_hop' THEN cost * 1.4
                       
                       -- Transfer penalties (but less for CBD transfers)
                       WHEN edge_type = 'transfer' THEN cost + 25.0
                       WHEN edge_type = 'walking' THEN cost + 15.0
                       
                       ELSE cost * 1.5
                   END as cost
            FROM cbd_edges
        """
        
        for origin_cand in origin_candidates:
                for dest_cand in dest_candidates:
                    total_attempts += 1
                    try:
                        # Try pgr_dijkstra with current penalty
                        route_sql = text("""
                            SELECT
                                1 as path_id,
                                r.seq,
                                r.node AS node_id,
                                r.edge,
                                s.stop_name,
                                s.stop_lat,
                                s.stop_lon,
                                e.route_id,
                                e.edge_type,
                                r.cost AS step_cost,
                                r.agg_cost AS total_cost
                            FROM pgr_dijkstra(
                                :routing_query,
                                :origin_node,
                                :dest_node,
                                directed := true
                            ) AS r
                            LEFT JOIN edges e ON r.edge = e.id
                            LEFT JOIN stages s ON r.node = s.node_id
                            WHERE s.stop_name IS NOT NULL
                            ORDER BY r.seq
                        """)

                        try:
                            route_result = conn.execute(route_sql, {
                                "routing_query": routing_query,
                                "origin_node": origin_cand._mapping["node_id"],
                                "dest_node": dest_cand._mapping["node_id"]
                            }).fetchall()
                        except Exception as sql_error:
                            # Rollback and continue with next candidate
                            try:
                                conn.rollback()
                            except:
                                pass
                            print(f"SQL error in routing query: {str(sql_error)}")
                            continue

                        if not route_result:
                            continue

                        successful_routes += 1

                        # Process route segments
                        segments = _process_route_segments(route_result)

                        if not segments:  # Skip if no valid segments
                            continue

                        transfers = max(0, len(segments) - 1)
                        transit_cost = route_result[-1]._mapping["total_cost"] if route_result else 0

                        # Calculate walking distances
                        origin_walk = origin_cand._mapping["walk_distance_m"]
                        dest_walk = dest_cand._mapping["walk_distance_m"]
                        total_walk = origin_walk + dest_walk

                        # CBD-aware scoring: favor routes that go through town for cross-corridor journeys
                        transfer_penalty = transfers * 600   # Reduced penalty since CBD routing may need transfers
                        walk_penalty = total_walk / 80       # Light walking penalty  
                        time_penalty = transit_cost * 1      # Normal transit time penalty
                        
                        # Check if route goes through CBD (bonus for town routing)
                        cbd_bonus = 0
                        total_cbd_stops = 0
                        for segment in segments:
                            cbd_stops = segment.get('cbd_stops', [])
                            total_cbd_stops += len(cbd_stops)
                        
                        if total_cbd_stops > 0:
                            cbd_bonus = -200 - (total_cbd_stops * 50)  # Bonus increases with more CBD stops
                            # Cap the bonus to prevent over-optimization
                            cbd_bonus = max(cbd_bonus, -500)
                        
                        # Directness bonuses
                        directness_bonus = 0
                        if transfers == 0:
                            directness_bonus = -400   # Best: direct routes
                        elif transfers == 1:
                            directness_bonus = -250   # Good: single transfer (especially through CBD)
                        elif transfers == 2:
                            directness_bonus = -100   # Decent: two transfers
                        elif transfers == 3:
                            directness_bonus = -25    # Acceptable: three transfers
                        
                        score = transfer_penalty + walk_penalty + time_penalty + directness_bonus + cbd_bonus

                        route_options.append({
                            "origin_candidate": {
                                "stop_id": origin_cand._mapping["stop_id"],
                                "stop_name": origin_cand._mapping["stop_name"],
                                "coordinates": {
                                    "lat": origin_cand._mapping["stop_lat"],
                                    "lon": origin_cand._mapping["stop_lon"]
                                },
                                "walking_distance_m": int(origin_walk),
                                "walking_time_min": int(origin_walk / 80)
                            },
                        "destination_candidate": {
                            "stop_id": dest_cand._mapping["stop_id"],
                            "stop_name": dest_cand._mapping["stop_name"],
                            "coordinates": {
                                "lat": dest_cand._mapping["stop_lat"],
                                "lon": dest_cand._mapping["stop_lon"]
                            },
                            "walking_distance_m": int(dest_walk),
                            "walking_time_min": int(dest_walk / 80)
                        },
                        "segments": segments,
                        "transfers": transfers,
                        "transit_cost": transit_cost,
                        "total_score": score,
                        "total_walking_distance_m": int(total_walk)
                        })
                        
                        # If we found a very good route (0-1 transfers), prioritize it
                        if transfers <= 1:
                            print(f"Found excellent route with {transfers} transfers, score: {score}")

                    except Exception as e:
                        # Rollback transaction and log the specific error for debugging
                        try:
                            conn.rollback()
                        except:
                            pass
                        print(f"Route failed between {origin_cand._mapping['stop_name']} and {dest_cand._mapping['stop_name']}: {str(e)}")
                        continue

        if not route_options:
            # Provide detailed debugging information
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No viable routes found between candidate stops",
                    "debug_info": {
                        "origin_candidates_found": len(origin_candidates),
                        "destination_candidates_found": len(dest_candidates),
                        "total_combinations_attempted": total_attempts,
                        "successful_routing_queries": successful_routes,
                        "origin_candidates": [c._mapping["stop_name"] for c in origin_candidates],
                        "dest_candidates": [c._mapping["stop_name"] for c in dest_candidates]
                    }
                }
            )

        # Sort by score and take best alternatives
        route_options.sort(key=lambda x: (x["transfers"], x["total_score"]))
        best_routes = route_options[:max_alternatives]

        # Get route labels for all routes
        all_route_ids = set()
        for route in best_routes:
            for seg in route["segments"]:
                if seg.get("route_id"):
                    all_route_ids.add(seg["route_id"])

        route_labels = {}
        if all_route_ids:
            label_sql = text("""
                SELECT route_id, route_short_name
                FROM routes
                WHERE route_id = ANY(:route_ids)
            """)
            label_rows = conn.execute(label_sql, {"route_ids": list(all_route_ids)}).fetchall()
            for row in label_rows:
                route_labels[row._mapping["route_id"]] = row._mapping["route_short_name"]

        # Add route labels and finalize response
        alternatives = []
        for i, route in enumerate(best_routes):
            # Add route labels to segments
            for seg in route["segments"]:
                seg["route_label"] = route_labels.get(seg.get("route_id"), seg.get("route_id", "Unknown"))

            # Count CBD stops and transfers through CBD
            total_cbd_stops = sum(len(seg.get("cbd_stops", [])) for seg in route["segments"])
            cbd_segments = [seg for seg in route["segments"] if seg.get("cbd_stops")]
            
            alternatives.append({
                "route_rank": i + 1,
                "origin": route["origin_candidate"],
                "destination": route["destination_candidate"],
                "transfers": route["transfers"],
                "segments": route["segments"],
                "total_walking_distance_m": route["total_walking_distance_m"],
                "estimated_total_time_min": (
                    route["origin_candidate"]["walking_time_min"] +
                    route["destination_candidate"]["walking_time_min"] +
                    len([stop for seg in route["segments"] for stop in seg["stops"]]) * 2
                ),
                "optimization_score": route["total_score"],
                "cbd_routing": {
                    "goes_through_cbd": total_cbd_stops > 0,
                    "total_cbd_stops": total_cbd_stops,
                    "cbd_segments": len(cbd_segments)
                }
            })

        return {
            "request": {
                "origin_coordinates": {"lat": origin_lat, "lon": origin_lon},
                "destination_coordinates": {"lat": dest_lat, "lon": dest_lon},
                "search_radius_m": search_radius
            },
            "alternatives_count": len(alternatives),
            "routes": alternatives,
            "optimization": {
                "candidates_tested": len(origin_candidates) * len(dest_candidates),
                "total_combinations_evaluated": len(route_options)
            }
        }


def _is_cbd_stop(stop_name, stop_lat=None, stop_lon=None):
    """
    Determine if a stop is in Nairobi's CBD based on name patterns or coordinates.
    CBD center approx: -1.286, 36.817
    """
    if not stop_name:
        return False
        
    # Known CBD stops and landmarks
    cbd_keywords = [
        'kencom', 'odeon', 'gpo', 'hilton', 'bus station', 'central', 
        'nation', 'city hall', 'parliament', 'uhuru', 'archives',
        'teleposta', 'ambassador', 'norfolk', 'stanley', 'jeevanjee',
        'tom mboya', 'ronald ngala', 'river road', 'moi avenue',
        'kenyatta avenue', 'haile selassie', 'university way',
        'museum hill', 'globe', 'integrity', 'anniversary', 'khoja'
    ]
    
    stop_lower = stop_name.lower()
    for keyword in cbd_keywords:
        if keyword in stop_lower:
            return True
    
    # If coordinates provided, check distance from CBD center
    if stop_lat is not None and stop_lon is not None:
        # Using simple distance calculation (can be enhanced with proper geospatial functions)
        cbd_center_lat, cbd_center_lon = -1.286, 36.817
        lat_diff = abs(stop_lat - cbd_center_lat)
        lon_diff = abs(stop_lon - cbd_center_lon)
        # Rough approximation: ~2km radius (about 0.018 degrees)
        if lat_diff <= 0.018 and lon_diff <= 0.018:
            return True
    
    return False


def _process_route_segments(route_rows):
    """Helper function to properly process route segments ensuring complete paths."""
    segments = []
    current_segment = None
    last_valid_route_id = None

    for i, row in enumerate(route_rows):
        route_id = row._mapping.get("route_id")
        stop_name = row._mapping.get("stop_name")
        stop_lat = row._mapping.get("stop_lat")
        stop_lon = row._mapping.get("stop_lon")
        edge_type = row._mapping.get("edge_type")
        seq = row._mapping.get("seq")
        edge_id = row._mapping.get("edge")

        # Skip rows without valid stop names
        if not stop_name:
            continue

        # Skip transfer edges (they don't represent actual travel)
        if edge_type == "transfer":
            continue

        # 🔥 FIX: Handle edge -1 (pgRouting virtual destination edge)
        if edge_id == -1 and not route_id and last_valid_route_id:
            route_id = last_valid_route_id
            print(f"Fixed edge -1 at destination '{stop_name}' with route_id '{route_id}'")

        # Handle missing route_id by inheriting from previous stop
        if not route_id and current_segment and current_segment.get("route_id"):
            route_id = current_segment["route_id"]
            print(f"Inherited route_id '{route_id}' for stop '{stop_name}' at seq {seq}")
        elif not route_id:
            print(f"Skipping stop '{stop_name}' with no route_id and no current segment")
            continue

        # Remember the last valid route_id for edge -1 handling
        if route_id and edge_id != -1:
            last_valid_route_id = route_id

        if current_segment is None:
            current_segment = {
                "route_id": route_id,
                "board": stop_name,
                "stops": [stop_name],
                "cbd_stops": []
            }
        else:
            if route_id != current_segment["route_id"]:
                # Transfer point - close current segment
                if len(current_segment["stops"]) >= 1:
                    current_segment["alight"] = current_segment["stops"][-1]
                    segments.append(current_segment)

                # Start new segment
                current_segment = {
                    "route_id": route_id,
                    "board": stop_name,
                    "stops": [stop_name],
                    "cbd_stops": []
                }
            else:
                # Same route, add stop if not duplicate
                if stop_name not in current_segment["stops"]:
                    current_segment["stops"].append(stop_name)
        
        # Track CBD stops in this segment
        if _is_cbd_stop(stop_name, stop_lat, stop_lon):
            if stop_name not in current_segment.get("cbd_stops", []):
                current_segment.setdefault("cbd_stops", []).append(stop_name)

    # Close final segment
    if current_segment and len(current_segment["stops"]) > 0:
        current_segment["alight"] = current_segment["stops"][-1]
        segments.append(current_segment)

    return segments


async def _expand_multi_hop_edge(conn, route_id, board_stop, alight_stop):
    """
    Expand multi-hop edges to show the complete journey path between stops.
    """
    try:
        # Query GTFS data to get the complete stop sequence
        expansion_sql = text("""
            SELECT DISTINCT s.stop_name, st.stop_sequence
            FROM stop_times st
            JOIN trips t ON st.trip_id = t.trip_id
            JOIN stages s ON st.stop_id = s.stop_id
            WHERE t.route_id = :route_id
              AND st.stop_sequence >= (
                  SELECT MIN(st2.stop_sequence) 
                  FROM stop_times st2 
                  JOIN trips t2 ON st2.trip_id = t2.trip_id
                  JOIN stages s2 ON st2.stop_id = s2.stop_id
                  WHERE t2.route_id = :route_id AND s2.stop_name = :board_stop
              )
              AND st.stop_sequence <= (
                  SELECT MAX(st3.stop_sequence) 
                  FROM stop_times st3 
                  JOIN trips t3 ON st3.trip_id = t3.trip_id
                  JOIN stages s3 ON st3.stop_id = s3.stop_id
                  WHERE t3.route_id = :route_id AND s3.stop_name = :alight_stop
              )
            ORDER BY st.stop_sequence
            LIMIT 20
        """)
        
        rows = conn.execute(expansion_sql, {
            "route_id": route_id,
            "board_stop": board_stop,
            "alight_stop": alight_stop
        }).fetchall()
        
        if rows and len(rows) > 1:
            return [row._mapping["stop_name"] for row in rows]
        else:
            return [board_stop, alight_stop] if board_stop != alight_stop else [board_stop]
            
    except Exception as e:
        # Rollback transaction on error to prevent cascade failures
        try:
            conn.rollback()
        except:
            pass
        print(f"Failed to expand multi-hop edge for route {route_id}: {str(e)}")
        return [board_stop, alight_stop] if board_stop != alight_stop else [board_stop]

