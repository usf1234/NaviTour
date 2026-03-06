# -*- coding: utf-8 -*-
"""
Created on Fri Feb 27 16:17:18 2026

@author: Samia
"""

# raptor/services/raptor_service.py

from raptor.algorithm import mc_raptor
from raptor.utils import extract_solutions, reconstruct, collapse_to_legs
from raptor.output_translation import load_translations, print_legs, print_segments
from raptor.services.stop_matcher import StopMatcher


import os as _os
translations_path = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "data", "translations.txt"
)
def run_raptor_from_assistant_json(network ,assistant_json, departure_time="08:00:00"):
    """
    Runs RAPTOR from Cairo assistant JSON.
    Returns formatted legs or an error message.
    """

    # -----------------------------
    # Initialize StopMatcher
    # -----------------------------
    stop_matcher = StopMatcher(network, translations_path)

    # -----------------------------
    # Extract origin & destination names
    # -----------------------------
    start_name = assistant_json.get("start_point", {}).get("official_name_ar")
    end_name = assistant_json.get("end_point", {}).get("official_name_ar")

    if not start_name or not end_name:
        return "Error: Missing origin or destination names"

    # -----------------------------
    # Match names to network stop IDs
    # -----------------------------
    origin_id = stop_matcher.match_with_fallback(start_name)
    destination_id = stop_matcher.match_with_fallback(end_name)

    if origin_id is None or destination_id is None:
        return f"Error: Could not find valid stops for '{start_name}' or '{end_name}'"

    print(f" Using stop {origin_id} for origin '{start_name}'")
    print(f" Using stop {destination_id} for destination '{end_name}'")

    # -----------------------------
    # Run RAPTOR
    # -----------------------------
    try:
        B, target = mc_raptor(network, origin_id, destination_id, departure_time)
    except KeyError as e:
        return f"Error: RAPTOR KeyError for stop {e}"


    # -----------------------------
    # Extract Pareto-optimal path
    # -----------------------------
    solutions = extract_solutions(B, target)
    if not solutions:
        return "Error: No solution found"

    segments = reconstruct(solutions[0])
    legs = collapse_to_legs(segments)
    # -----------------------------
    # Load stop translations for readable output
    # -----------------------------
    stop_name_func = load_translations(translations_path, network)
    

    # Optional: print nicely
    print_legs(legs, stop_name_func)
    print_segments(segments, stop_name_func)

    return legs
