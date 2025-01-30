from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
import requests
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from route.models import FuelStop
from utils.state_abbreviations import STATE_ABBREVIATIONS
import pandas as pd
import folium
from django.conf import settings

# Initialize OpenRouteService client
ORS_API_KEY = "5b3ce3597851110001cf624858de3b9e5b4e4608917551d62a90382e"
MAX_RANGE_MILES = 440
MPG = 10  # Miles per gallon

def route_optimize(request):
    headers = {
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
    }
    starting_point = (-74.005974, 40.712776)  # Example: New York
    end_point = '-87.629799, 41.878113'  # Example: Chicago

    call = requests.get(f'https://api.openrouteservice.org/v2/directions/driving-car?api_key={ORS_API_KEY}&start={starting_point[0]},{starting_point[1]}&end={end_point}', headers=headers)
    data = call.json()

    # Extract route coordinates
    route_coords = data['features'][0]['geometry']['coordinates']  # [[lon, lat], [lon, lat], ...]
    
    start_state = get_state(starting_point[1], starting_point[0])
    initial_fuel_stop = get_cheapest_fuel_stop_by_state(retrieve_fuel_stops_by_state(start_state))
    
    fuel_stops_list = [initial_fuel_stop.iloc[0].to_dict()] if not initial_fuel_stop.empty else []
    current_index = 0
    current_stop = starting_point
    total_cost = 0
    if geodesic(current_stop, tuple(reversed(route_coords[-1]))).miles >= MAX_RANGE_MILES:
        total_cost += (MAX_RANGE_MILES / MPG) * float(initial_fuel_stop.iloc[0]['retail_price'])
    else:
        total_cost += (geodesic(current_stop, tuple(reversed(route_coords[-1]))).miles / MPG) * float(initial_fuel_stop.iloc[0]['retail_price'])          

    while geodesic(current_stop, tuple(reversed(route_coords[-1]))).miles >= MAX_RANGE_MILES:
        # Find the next 500-mile point
        mile_500_coord = binary_search_500_miles(route_coords[current_index:])
        current_stop = mile_500_coord

        # Get the state of the 500-mile point
        state = get_state(mile_500_coord[0], mile_500_coord[1])
        print(f"State at 500 miles: {state}")

        # Retrieve fuel stops in that state
        fuel_stops = retrieve_fuel_stops_by_state(state)

        # Find the cheapest fuel stop
        cheapest_stop = get_cheapest_fuel_stop_by_state(fuel_stops)

        if not cheapest_stop.empty:
            selected_fuel_stop = cheapest_stop.iloc[0].to_dict()  # Get the cheapest stop
            fuel_stops_list.append(selected_fuel_stop)

        # Check remaining distance from this stop to the destination
        remaining_distance = geodesic(current_stop, tuple(reversed(route_coords[-1]))).miles
        print(f"Remaining distance from current_stop:{current_stop} to endpoint:{route_coords[-1]} is: {remaining_distance} miles")

        # If the remaining distance is less than 500 miles, stop searching
        if remaining_distance < MAX_RANGE_MILES:
            total_cost += (remaining_distance / MPG) * float(cheapest_stop.iloc[0]['retail_price'])
            break  # Exit loop, no more stops needed
        else:
            total_cost += (MAX_RANGE_MILES / MPG) * float(cheapest_stop.iloc[0]['retail_price'])

        # Otherwise, continue searching for another fuel stop
        current_index = route_coords.index(list(reversed(mile_500_coord)))  # Update search index

    map = generate_map(route_coords, request)
    
    return JsonResponse({
        "fuel_stops": fuel_stops_list,
        "total_cost": round(total_cost, 2),
        "map_url": map
    })

def binary_search_500_miles(route_coords):
    """
    Perform binary search to efficiently find the closest point to 500 miles.
    This method avoids full traversal.
    """
    left, right = 0, len(route_coords) - 1
    target_distance = MAX_RANGE_MILES

    while left < right:
        mid = (left + right) // 2
        mid_point = tuple(reversed(route_coords[mid]))  # Convert [lon, lat] to (lat, lon)
        start_point = tuple(reversed(route_coords[0]))  # First point in the route

        # Compute distance only for mid-point
        mid_distance = geodesic(start_point, mid_point).miles
        print(f"Distance from start:{start_point} to mid-point:{mid_point} is: {mid_distance} miles")

        if mid_distance < target_distance:
            left = mid + 1
        else:
            right = mid

    return tuple(reversed(route_coords[left]))

def get_state(lat, lon):
    geolocator = Nominatim(user_agent="fuel_stop_locator")
    location = geolocator.reverse((lat, lon), language="en", exactly_one=True)
    
    if location:
        address = location.raw.get('address', {})
        full_state = address.get('state', '')
        state = STATE_ABBREVIATIONS.get(full_state, full_state)
        return state
    else:
        return None, None
    
def retrieve_fuel_stops_by_state(state):
    """Retrieve all fuel stops in the given state from the database."""
    return FuelStop.objects.filter(state=state)

def get_cheapest_fuel_stop_by_state(fuel_stops):
    # Convert the queryset to a pandas DataFrame
    fuel_stops_df = pd.DataFrame(list(fuel_stops.values()))

    cheapest_stops = []
    
    # Group by state
    for state, group in fuel_stops_df.groupby('state'):  # Ensure you're using the correct column name here
        # Find the cheapest stop within this state
        cheapest_stop = group.loc[group['retail_price'].idxmin()]  # Ensure you're using the correct column name here
        cheapest_stops.append(cheapest_stop)
    
    # Return a DataFrame of the cheapest stops for each state
    return pd.DataFrame(cheapest_stops)

geolocator = Nominatim(user_agent="fuel_stop_locator")
def get_lat_lon(address):
    """Convert an address to latitude & longitude using Geopy"""
    location = geolocator.geocode(address)
    if location:
        return (location.latitude, location.longitude)
    return None

def generate_map(route_coords, request):
    """Generate a Folium map with the route."""
    
    start_coord = tuple(reversed(route_coords[0]))  # Convert (lng, lat) → (lat, lng)
    end_coord = tuple(reversed(route_coords[-1]))

    my_map = folium.Map(location=start_coord, zoom_start=6)
    
    # Add route polyline
    folium.PolyLine([tuple(reversed(coord)) for coord in route_coords], color="blue", weight=4).add_to(my_map)

    # Add start and end markers
    folium.Marker(start_coord, popup="Start Point", icon=folium.Icon(color="green")).add_to(my_map)
    folium.Marker(end_coord, popup="End Point", icon=folium.Icon(color="blue")).add_to(my_map)

    # Save map to static directory
    map_filename = "route_map.html"
    map_path = f"{settings.BASE_DIR}/static/{map_filename}"
    my_map.save(map_path)

    # Return the URL to access the map
    map_url = request.build_absolute_uri(f"/static/{map_filename}")

    return my_map


