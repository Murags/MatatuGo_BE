from fastapi import APIRouter, Query
from typing import Optional
from ..crud import routes

router = APIRouter(prefix="/routes", tags=["Routing"])


@router.get("/")
async def get_route(origin: str, destination: str):
    """
    Get the best route between two stops including transfer points.
    Input: stop names (partial allowed)
    Output: structured JSON with board/alight actions and route info
    """
    return await routes.get_route(origin, destination)



@router.get("/by-coordinates")
async def get_route_by_coordinates(
    origin_lat: float = Query(..., description="Origin latitude", ge=-90, le=90),
    origin_lon: float = Query(..., description="Origin longitude", ge=-180, le=180),
    dest_lat: float = Query(..., description="Destination latitude", ge=-90, le=90),
    dest_lon: float = Query(..., description="Destination longitude", ge=-180, le=180),
    search_radius: int = Query(500, description="Search radius in meters", ge=100, le=2000),
    max_candidates: int = Query(5, description="Max candidate stops to consider", ge=3, le=10),
    alternatives: int = Query(3, description="Number of alternative routes", ge=1, le=5)
):
    """
    Get multiple alternative routes between coordinates by finding optimal nearby stops.

    This endpoint:
    1. Finds multiple candidate stops near origin and destination
    2. Tests routing combinations between candidates using k-shortest paths
    3. Returns multiple route alternatives with least transfers and reasonable walking distance

    - **origin_lat**: Origin latitude (e.g., -1.28197 for Odeon)
    - **origin_lon**: Origin longitude (e.g., 36.82175 for Odeon)
    - **dest_lat**: Destination latitude (e.g., -1.26965 for Kangemi)
    - **dest_lon**: Destination longitude (e.g., 36.74823 for Kangemi)
    - **search_radius**: How far to look for candidate stops (meters)
    - **max_candidates**: Maximum stops to consider per location
    - **alternatives**: Number of alternative routes to return
    """
    return await routes.get_route_by_coordinates(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        search_radius=search_radius,
        max_candidates=max_candidates,
        max_alternatives=alternatives
    )


@router.get("/alternatives")
async def get_alternative_routes(
    origin: str,
    destination: str,
    max_alternatives: int = Query(3, ge=1, le=5, description="Number of alternative routes")
):
    """
    Get multiple alternative routes between two stops.
    """
    return await routes.get_route(origin, destination, max_alternatives=max_alternatives)


@router.get("/by-coordinates-llm")
async def get_route_by_coordinates_llm(
    origin_lat: float = Query(..., description="Origin latitude", ge=-90, le=90),
    origin_lon: float = Query(..., description="Origin longitude", ge=-180, le=180),
    dest_lat: float = Query(..., description="Destination latitude", ge=-90, le=90),
    dest_lon: float = Query(..., description="Destination longitude", ge=-180, le=180),
    search_radius: int = Query(500, description="Search radius in meters", ge=100, le=2000),
    max_candidates: int = Query(5, description="Max candidate stops to consider", ge=3, le=10)
):
    """
    Get route alternatives using AI (GPT-4o-mini) based on coordinates.

    This endpoint uses an LLM to suggest the 3 cheapest/best matatu routes:
    1. Finds nearby stops at origin and destination coordinates
    2. Gets available matatu routes from the database
    3. Uses GPT-4o-mini to suggest optimal routes based on Nairobi knowledge

    The LLM considers:
    - Cost efficiency (fewer transfers = cheaper)
    - Well-known, reliable matatu routes
    - Direct routes when possible
    - Typical Nairobi matatu fares (30-80 KSh per segment)

    - **origin_lat**: Origin latitude (e.g., -1.28197 for Odeon)
    - **origin_lon**: Origin longitude (e.g., 36.82175 for Odeon)
    - **dest_lat**: Destination latitude (e.g., -1.26965 for Kangemi)
    - **dest_lon**: Destination longitude (e.g., 36.74823 for Kangemi)
    - **search_radius**: How far to look for nearby stops (meters)
    - **max_candidates**: Maximum stops to consider per location
    """
    return await routes.get_route_by_coordinates_llm(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        search_radius=search_radius,
        max_candidates=max_candidates
    )


@router.get("/cbd-fallback")
async def get_route_via_cbd_fallback(
    origin_lat: float = Query(..., description="Origin latitude", ge=-90, le=90),
    origin_lon: float = Query(..., description="Origin longitude", ge=-180, le=180),
    dest_lat: float = Query(..., description="Destination latitude", ge=-90, le=90),
    dest_lon: float = Query(..., description="Destination longitude", ge=-180, le=180),
    search_radius: int = Query(500, description="Search radius in meters", ge=100, le=2000),
    max_candidates: int = Query(5, description="Max candidate stops to consider", ge=3, le=10)
):
    """
    Intelligent CBD-centric fallback routing:

    This endpoint implements a smart routing strategy:
    1. **First**: Try direct routes (0-1 transfers)
    2. **If no good direct route**: Route through CBD (Nairobi town center)
       - Find routes from Origin → CBD transfer hubs
       - Find routes from CBD transfer hubs → Destination
       - Connect them at major CBD stops

    This mirrors how Nairobi commuters actually travel - many routes go through town!

    Benefits:
    - Always finds a route even for distant/disconnected areas
    - Leverages Nairobi's hub-and-spoke transit network
    - Uses major CBD transfer points (Kencom, GPO, Hilton, etc.)
    - Combines multiple matatus efficiently

    Response includes:
    - `routing_strategy`: "direct" or "town_fallback"
    - Coordinates for origin and destination

    - **origin_lat**: Origin latitude
    - **origin_lon**: Origin longitude
    - **dest_lat**: Destination latitude
    - **dest_lon**: Destination longitude
    - **search_radius**: How far to look for nearby stops (meters)
    - **max_candidates**: Maximum stops to consider per location
    """
    return await routes.get_route_by_coordinates(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        search_radius=search_radius,
        max_candidates=max_candidates
    )
