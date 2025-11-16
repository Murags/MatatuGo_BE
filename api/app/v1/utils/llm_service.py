import logging
from openai import OpenAI
from typing import List, Dict, Any
import json
from ...config import settings

# logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.openai_api_key)


async def get_llm_routes(
    origin_stop: str,
    destination_stop: str,
    origin_coords: Dict[str, float],
    dest_coords: Dict[str, float],
    available_routes: List[str],
    nearby_stops: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    """
    Use GPT-4o to find the 3 cheapest/best routes from origin to destination.

    Args:
        origin_stop: Name of the origin stop
        destination_stop: Name of the destination stop
        available_routes: List of available matatu route numbers in the system
        nearby_stops: Dictionary with origin and destination nearby stops

    Returns:
        List of route alternatives with steps, costs, and matatu numbers
    """

    system_prompt = """You are a Nairobi matatu route expert. Given an origin and destination with their coordinates, \
    suggest 3 alternative routes using matatus.

    IMPORTANT: Use the coordinates as your PRIMARY guide for route planning. Stop names may be generic or ambiguous, \
    but the coordinates (-1.xxx, 36.xxx format) will tell you the exact location in Nairobi. Pay close attention to the \
    lat/lon values to determine the actual area and neighborhood.

    Each route should have:
    - route_name: A descriptive name showing the path (e.g., "Westlands → Ngara → Roysambu")
    - steps: Array of steps, each with:
      - board_stop: Where to board the matatu (use the nearest major landmark if stop name is generic)
      - board_stop_coords: Coordinates of the boarding stop (format: {"lat": -1.xxx, "lon": 36.xxx})
      - matatu_number: The matatu route number to take (e.g., "23", "46", "125")
      - to_stop: Where to alight (matatus may drop passengers at the nearest point along their route, not always exactly at destination)
      - to_stop_coords: Coordinates of the alighting stop (format: {"lat": -1.xxx, "lon": 36.xxx})
      - walking_distance_m: Estimated walking distance from alighting point to actual destination (if applicable)
      - approx_cost_KSh: Approximate cost in Kenyan Shillings (typically 30-80 KSh per segment)
    - total_estimated_cost_KSh: Sum of all segment costs

    IMPORTANT NOTES:
    - Matatus follow fixed routes and may not drop you exactly at your destination. Suggest the nearest stop along the route where passengers can alight and walk to the final destination.
    - Always provide realistic coordinates for boarding and alighting stops.
    - Use actual Nairobi matatu route NUMBERS (not names), like "23", "46", "125", "111", etc.

    Prioritize:
    1. Cheapest routes (fewer transfers = cheaper)
    2. Well-known, reliable routes
    3. Direct routes over multiple transfers when possible. If a direct route is not feasible, suggest routes that go through Nairobi Central Business District (CBD) if it makes sense for efficient travel).

    Base your response on actual Nairobi matatu routes and typical fares. Use the coordinates to accurately identify the neighborhoods and suggest appropriate routes."""

    user_prompt = f"""Find 3 alternative routes between these two locations in Nairobi:

    ORIGIN: {origin_stop}
    Coordinates: {origin_coords.get('latitude')}, {origin_coords.get('longitude')}
    Nearby stops: {', '.join(nearby_stops.get('origin', [origin_stop])[:5])}

    DESTINATION: {destination_stop}
    Coordinates: {dest_coords.get('latitude')}, {dest_coords.get('longitude')}
    Nearby stops: {', '.join(nearby_stops.get('destination', [destination_stop])[:5])}

    Available route numbers in the system: {', '.join(available_routes[:50])}

    CRITICAL: Focus primarily on the COORDINATES to determine the actual location and neighborhood. The stop names may be generic, \
    but the coordinates will tell you exactly where in Nairobi these locations are. Identify the neighborhoods from the coordinates \
    and suggest accurate matatu routes between them.

    Return ONLY a valid JSON object with a "routes" key containing an array of 3 route options. No markdown, no explanation."""

    print("Making OpenAI API call...")
    print(f"Model: gpt-4o, Temperature: 0.7, Max tokens: 2000")

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # Changed from gpt-4o-mini
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )

        print(f"OpenAI API call successful - tokens used: {response.usage.total_tokens if response.usage else 'unknown'}")

        result_text = response.choices[0].message.content

        # Parse the JSON response
        print(f"Parsing LLM response (length: {len(result_text)} chars)")
        print(f"Raw LLM response: {result_text[:500]}{'...' if len(result_text) > 500 else ''}")

        try:
            result = json.loads(result_text)
            print("Successfully parsed JSON response")
            # Handle if the response is wrapped in a "routes" key
            if isinstance(result, dict) and "routes" in result:
                routes = result["routes"]
                print(f"Extracted {len(routes)} routes from 'routes' key")
                return routes
            elif isinstance(result, list):
                print(f"Response is direct list of {len(result)} routes")
                return result
            else:
                print(f"Unexpected response structure: {type(result)}")
                return result
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            # Fallback: try to extract JSON from markdown code blocks
            if "```json" in result_text:
                print("Attempting to extract JSON from markdown code blocks")
                json_str = result_text.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_str)
                if isinstance(result, dict) and "routes" in result:
                    routes = result["routes"]
                    print(f"Successfully extracted {len(routes)} routes from markdown")
                    return routes
                print("Successfully parsed JSON from markdown")
                return result
            print("Failed to parse JSON response")
            raise

    except Exception as e:
        print(f"LLM API call failed: {str(e)}")
        # Check if it's a quota/rate limit error
        error_str = str(e).lower()
        if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
            print("API quota/rate limit exceeded - using fallback routes")
            # Return fallback routes when API quota is exceeded
            return get_fallback_routes(origin_stop, destination_stop, available_routes)

        print(f"Raising exception for LLM failure: {str(e)}")
        raise Exception(f"LLM routing failed: {str(e)}")


def get_fallback_routes(origin_stop: str, destination_stop: str, available_routes: List[str]) -> List[Dict[str, Any]]:
    """
    Provide fallback routes when LLM API is unavailable due to quota limits.
    Returns basic route suggestions using available route numbers.
    """
    print(f"Generating fallback routes for {origin_stop} -> {destination_stop}")
    print(f"Available routes: {len(available_routes)} total")

    # Get a few route numbers to suggest (limit to 3-4)
    suggested_routes = available_routes[:4] if len(available_routes) >= 4 else available_routes
    print(f"Using {len(suggested_routes)} routes for fallback: {suggested_routes}")

    routes = []
    for i, route in enumerate(suggested_routes[:3], 1):  # Max 3 routes
        route_data = {
            "route_name": f"{origin_stop} → Direct Route {i} → {destination_stop}",
            "steps": [
                {
                    "board_stop": origin_stop,
                    "board_stop_coords": {"lat": None, "lon": None}, # Added
                    "matatu_number": route,
                    "to_stop": destination_stop,
                    "to_stop_coords": {"lat": None, "lon": None}, # Added
                    "walking_distance_m": 0, # Added
                    "approx_cost_KSh": 50
                }
            ],
            "total_estimated_cost_KSh": 50
        }
        routes.append(route_data)
        print(f"Created fallback route {i}: {route_data['route_name']} using matatu {route}")

    print(f"Generated {len(routes)} fallback routes")
    return routes


def format_llm_response(llm_routes: List[Dict[str, Any]], origin_stop: str, destination_stop: str) -> Dict[str, Any]:
    """
    Format the LLM response to match the existing route response structure.

    Args:
        llm_routes: Raw LLM response with route alternatives
        origin_stop: Origin stop name
        destination_stop: Destination stop name

    Returns:
        Formatted response matching existing structure
    """
    print(f"Formatting {len(llm_routes)} LLM routes for response")
    alternatives = []

    for idx, route in enumerate(llm_routes, 1):
        steps = []
        total_cost = route.get("total_estimated_cost_KSh", 0)

        for step in route.get("steps", []):
            board_coords = step.get("board_stop_coords", {})
            to_coords = step.get("to_stop_coords", {})

            steps.append({
                "action": "board",
                "stop_name": step.get("board_stop", ""),
                "coordinates": {
                    "lat": board_coords.get("lat") if isinstance(board_coords, dict) else None,
                    "lon": board_coords.get("lon") if isinstance(board_coords, dict) else None
                },
                "route_id": step.get("matatu_number", ""),
                "estimated_cost_ksh": step.get("approx_cost_KSh", 0)
            })
            steps.append({
                "action": "alight",
                "stop_name": step.get("to_stop", ""),
                "coordinates": {
                    "lat": to_coords.get("lat") if isinstance(to_coords, dict) else None,
                    "lon": to_coords.get("lon") if isinstance(to_coords, dict) else None
                },
                "route_id": step.get("matatu_number", ""),
                "estimated_cost_ksh": 0,
                "walking_distance_m": step.get("walking_distance_m", 0) # Added
            })

        alternatives.append({
            "alternative": idx,
            "route_name": route.get("route_name", f"Route {idx}"),
            "total_estimated_cost_ksh": total_cost,
            "number_of_transfers": len(route.get("steps", [])) - 1,
            "steps": steps
        })

    return {
        "origin": origin_stop,
        "destination": destination_stop,
        "alternatives": alternatives,
        "routing_method": "llm",
        "model": "gpt-4o" # Changed from gpt-4o-mini
    }

