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
