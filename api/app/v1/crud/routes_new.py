import logging
from fastapi import HTTPException
from sqlalchemy import text
from ...database import database_session_manager
from ..utils.llm_service import get_llm_routes, format_llm_response

# logger = logging.getLogger(__name__)

async def get_route(origin: str, destination: str, max_alternatives: int = 3):
    """Get traditional routes by stop name"""
    print(f"=== ROUTING REQUEST ===")
    print(f"Origin: '{origin}', Destination: '{destination}'")
    print(f"Max alternatives: {max_alternatives}")

    origin = origin.strip()
    destination = destination.strip()
    TRANSFER_PENALTY = 10.0

    with database_session_manager.engine.connect() as conn:
        try:
            conn.execute(text("SELECT pgr_version()")).fetchone()
        except Exception:
            raise HTTPException(status_code=503, detail="pgRouting extension not available")

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

        pgrouting_query = f"""
            WITH base AS (
                SELECT id, source_id AS source, target_id AS target, 1.0 AS hop_cost, route_id
                FROM edges
                WHERE cost IS NOT NULL
            ),
            penalized AS (
                SELECT id, source, target,
                       CASE
                           WHEN LAG(route_id) OVER (ORDER BY id) = route_id THEN hop_cost
                           ELSE hop_cost + {TRANSFER_PENALTY}
                       END AS cost
                FROM base
            )
            SELECT id, source, target, cost FROM penalized
        """

        routing_sql = text("""
            SELECT p.path_id, p.seq, p.node AS node_id, p.edge, s.stop_name, e.route_id,
                   p.cost AS step_cost, p.agg_cost AS total_cost
            FROM pgr_ksp(:query, :origin_node, :dest_node, :k, directed := true) AS p
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
            raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")

        if not rows:
            raise HTTPException(status_code=404, detail="No route found")

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
                    path_data["current_segment"]["alight"] = path_data["current_segment"]["stops"][-1]
                    path_data["segments"].append(path_data["current_segment"])
                    path_data["current_segment"] = {
                        "route_id": route_id,
                        "board": stop_name,
                        "stops": [stop_name]
                    }
                else:
                    path_data["current_segment"]["stops"].append(stop_name)

        for path_data in routes_by_path.values():
            if path_data["current_segment"]:
                path_data["current_segment"]["alight"] = path_data["current_segment"]["stops"][-1]
                path_data["segments"].append(path_data["current_segment"])

        all_route_ids = set()
        for path_data in routes_by_path.values():
            for segment in path_data["segments"]:
                if segment["route_id"]:
                    all_route_ids.add(segment["route_id"])

        route_map = {}
        if all_route_ids:
            label_sql = text("""
                SELECT route_id, route_short_name FROM routes WHERE route_id = ANY(:route_ids)
            """)
            label_rows = conn.execute(label_sql, {"route_ids": list(all_route_ids)}).fetchall()
            for r in label_rows:
                route_map[r._mapping["route_id"]] = r._mapping["route_short_name"]

        alternatives = []
        for path_id in sorted(routes_by_path.keys()):
            path_data = routes_by_path[path_id]
            for seg in path_data["segments"]:
                seg["route_label"] = route_map.get(seg["route_id"], seg["route_id"])

            alternatives.append({
                "route_rank": len(alternatives) + 1,
                "total_cost": path_data["total_cost"],
                "transfers": max(0, len(path_data["segments"]) - 1),
                "segments": path_data["segments"],
                "estimated_duration": len([stop for seg in path_data["segments"] for stop in seg["stops"]]) * 2
            })

        alternatives.sort(key=lambda x: (x["transfers"], x["total_cost"]))

        return {
            "origin": origin_row._mapping["stop_name"],
            "destination": dest_row._mapping["stop_name"],
            "alternatives_count": len(alternatives),
            "routes": alternatives[:max_alternatives]
        }


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
    DIRECT-FIRST + TOWN-FALLBACK ROUTING:

    1. Try direct routes first (origin → destination)
    2. If no good direct route (>1 transfer), route through town:
       - Origin → Town (2.5km radius around CBD center)
       - Town → Destination
    3. Return best alternatives
    """

    # Nairobi CBD center
    TOWN_LAT, TOWN_LON = -1.2848863468680394, 36.82599683396185
    TOWN_RADIUS = 2500  # 2.5km radius

    print(f"=== DIRECT-FIRST + TOWN-FALLBACK ROUTING ===")
    print(f"Origin: ({origin_lat}, {origin_lon})")
    print(f"Destination: ({dest_lat}, {dest_lon})")

    with database_session_manager.engine.connect() as conn:
        # Step 1: Find nearby stops at origin, town, and destination
        print("Finding nearby stops...")

        def find_stops(lat, lon, radius, label):
            sql = text("""
                SELECT stop_id, stop_name, node_id, stop_lat, stop_lon,
                       ST_DistanceSphere(ST_MakePoint(stop_lon, stop_lat),
                                       ST_MakePoint(:lon, :lat)) AS walk_distance_m
                FROM stages
                WHERE ST_DistanceSphere(ST_MakePoint(stop_lon, stop_lat),
                                      ST_MakePoint(:lon, :lat)) <= :radius
                ORDER BY walk_distance_m
                LIMIT :max_candidates
            """)
            stops = conn.execute(sql, {
                "lat": lat, "lon": lon, "radius": radius, "max_candidates": max_candidates
            }).fetchall()
            print(f"  {label}: Found {len(stops)} stops")
            return stops

        origin_stops = find_stops(origin_lat, origin_lon, search_radius, "Origin")
        dest_stops = find_stops(dest_lat, dest_lon, search_radius, "Destination")
        town_stops = find_stops(TOWN_LAT, TOWN_LON, TOWN_RADIUS, "Town")

        if not origin_stops or not dest_stops:
            raise HTTPException(status_code=404, detail="No stops found at origin or destination")

        if not town_stops:
            print("  WARNING: No town stops found, will try direct only")

        # Step 2: Try direct routing first
        print("Trying direct routing...")
        direct_routes = []

        for origin_stop in origin_stops[:2]:
            for dest_stop in dest_stops[:2]:
                try:
                    route_sql = text("""
                        SELECT r.seq, r.node, r.edge, r.cost, r.agg_cost,
                               s.stop_name, e.route_id, e.edge_type
                        FROM pgr_dijkstra(
                            'SELECT id, source_id AS source, target_id AS target, cost FROM edges WHERE cost > 0',
                            :origin_node, :dest_node, directed := true
                        ) AS r
                        LEFT JOIN edges e ON r.edge = e.id
                        LEFT JOIN stages s ON r.node = s.node_id
                        WHERE s.stop_name IS NOT NULL
                        ORDER BY r.seq
                    """)

                    route_result = conn.execute(route_sql, {
                        "origin_node": origin_stop._mapping["node_id"],
                        "dest_node": dest_stop._mapping["node_id"]
                    }).fetchall()

                    if route_result:
                        segments = _process_route_segments(route_result)
                        if segments:
                            transfers = max(0, len(segments) - 1)
                            cost = route_result[-1]._mapping["agg_cost"]

                            direct_routes.append({
                                "origin_stop": origin_stop._mapping,
                                "dest_stop": dest_stop._mapping,
                                "segments": segments,
                                "transfers": transfers,
                                "cost": cost,
                                "routing_type": "direct"
                            })
                            print(f"  Found direct route: {transfers} transfers, cost {cost:.2f}")
                except:
                    continue

        # If we found good direct routes (≤1 transfer), return them
        if direct_routes:
            direct_routes.sort(key=lambda x: (x["transfers"], x["cost"]))
            good_routes = [r for r in direct_routes if r["transfers"] <= 1][:max_alternatives]
            if good_routes:
                print(f"✓ Using direct routes ({len(good_routes)} found)")
                return _format_routes_response(good_routes, "direct")

        # Step 3: Town fallback - route through town center
        print("Using town fallback routing...")

        if not town_stops:
            raise HTTPException(status_code=404, detail="No routes found (direct or via town)")

        town_routes = []

        # Origin → Town routes
        origin_to_town = []
        for origin_stop in origin_stops[:2]:
            for town_stop in town_stops[:5]:
                try:
                    route_sql = text("""
                        SELECT r.seq, r.node, r.edge, r.cost, r.agg_cost,
                               s.stop_name, e.route_id, e.edge_type
                        FROM pgr_dijkstra(
                            'SELECT id, source_id AS source, target_id AS target, cost FROM edges WHERE cost > 0',
                            :origin_node, :town_node, directed := true
                        ) AS r
                        LEFT JOIN edges e ON r.edge = e.id
                        LEFT JOIN stages s ON r.node = s.node_id
                        WHERE s.stop_name IS NOT NULL
                        ORDER BY r.seq
                    """)

                    route_result = conn.execute(route_sql, {
                        "origin_node": origin_stop._mapping["node_id"],
                        "town_node": town_stop._mapping["node_id"]
                    }).fetchall()

                    if route_result:
                        segments = _process_route_segments(route_result)
                        if segments:
                            origin_to_town.append({
                                "origin_stop": origin_stop._mapping,
                                "town_stop": town_stop._mapping,
                                "segments": segments,
                                "transfers": max(0, len(segments) - 1),
                                "cost": route_result[-1]._mapping["agg_cost"]
                            })
                except:
                    continue

        # Town → Destination routes
        town_to_dest = []
        for town_stop in town_stops[:5]:
            for dest_stop in dest_stops[:2]:
                try:
                    route_sql = text("""
                        SELECT r.seq, r.node, r.edge, r.cost, r.agg_cost,
                               s.stop_name, e.route_id, e.edge_type
                        FROM pgr_dijkstra(
                            'SELECT id, source_id AS source, target_id AS target, cost FROM edges WHERE cost > 0',
                            :town_node, :dest_node, directed := true
                        ) AS r
                        LEFT JOIN edges e ON r.edge = e.id
                        LEFT JOIN stages s ON r.node = s.node_id
                        WHERE s.stop_name IS NOT NULL
                        ORDER BY r.seq
                    """)

                    route_result = conn.execute(route_sql, {
                        "town_node": town_stop._mapping["node_id"],
                        "dest_node": dest_stop._mapping["node_id"]
                    }).fetchall()

                    if route_result:
                        segments = _process_route_segments(route_result)
                        if segments:
                            town_to_dest.append({
                                "town_stop": town_stop._mapping,
                                "dest_stop": dest_stop._mapping,
                                "segments": segments,
                                "transfers": max(0, len(segments) - 1),
                                "cost": route_result[-1]._mapping["agg_cost"]
                            })
                except:
                    continue

        if not origin_to_town or not town_to_dest:
            raise HTTPException(status_code=404, detail="Could not find routes through town")

        # Combine O→T and T→D routes
        for o2t in origin_to_town[:3]:
            for t2d in town_to_dest[:3]:
                if o2t["town_stop"]["stop_id"] == t2d["town_stop"]["stop_id"]:
                    combined = {
                        "origin_stop": o2t["origin_stop"],
                        "dest_stop": t2d["dest_stop"],
                        "town_transfer": o2t["town_stop"],
                        "segments": o2t["segments"] + t2d["segments"],
                        "transfers": o2t["transfers"] + t2d["transfers"] + 1,
                        "cost": o2t["cost"] + t2d["cost"] + 15,
                        "routing_type": "town_fallback"
                    }
                    town_routes.append(combined)

        if not town_routes:
            raise HTTPException(status_code=404, detail="Could not combine routes through town")

        town_routes.sort(key=lambda x: (x["transfers"], x["cost"]))
        best_town_routes = town_routes[:max_alternatives]

        print(f"✓ Using town fallback routes ({len(best_town_routes)} found)")
        return _format_routes_response(best_town_routes, "town_fallback")


def _process_route_segments(route_rows):
    """Helper function to process route segments"""
    segments = []
    current_segment = None
    last_valid_route_id = None

    for i, row in enumerate(route_rows):
        route_id = row._mapping.get("route_id")
        stop_name = row._mapping.get("stop_name")
        edge_type = row._mapping.get("edge_type")
        edge_id = row._mapping.get("edge")

        if not stop_name:
            continue

        if edge_type == "transfer":
            continue

        if edge_id == -1 and not route_id and last_valid_route_id:
            route_id = last_valid_route_id

        if not route_id and current_segment and current_segment.get("route_id"):
            route_id = current_segment["route_id"]
        elif not route_id:
            continue

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
                if len(current_segment["stops"]) >= 1:
                    current_segment["alight"] = current_segment["stops"][-1]
                    segments.append(current_segment)

                current_segment = {
                    "route_id": route_id,
                    "board": stop_name,
                    "stops": [stop_name],
                    "cbd_stops": []
                }
            else:
                if stop_name not in current_segment["stops"]:
                    current_segment["stops"].append(stop_name)

    if current_segment and len(current_segment["stops"]) > 0:
        current_segment["alight"] = current_segment["stops"][-1]
        segments.append(current_segment)

    return segments


def _format_routes_response(routes, routing_type):
    """Format routes into response structure"""
    alternatives = []

    for i, route in enumerate(routes, 1):
        steps = []
        for segment in route["segments"]:
            steps.append({
                "board": segment["board"],
                "alight": segment["alight"],
                "route_id": segment["route_id"],
                "stops": segment["stops"],
                "stop_count": len(segment["stops"])
            })

        alternatives.append({
            "rank": i,
            "transfers": route["transfers"],
            "cost": route["cost"],
            "steps": steps
        })

    return {
        "routing_strategy": routing_type,
        "alternatives_count": len(alternatives),
        "routes": alternatives
    }


async def get_route_by_coordinates_llm(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    search_radius: int = 500,
    max_candidates: int = 5
):
    """LLM-based routing"""
    print(f"=== LLM ROUTING REQUEST ===")
    print(f"Origin: ({origin_lat}, {origin_lon})")
    print(f"Destination: ({dest_lat}, {dest_lon})")

    # Placeholder for LLM routing
    raise HTTPException(status_code=501, detail="LLM routing not yet implemented")


