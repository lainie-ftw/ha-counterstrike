#!/usr/bin/env python3
"""
PandaScore API tester for Counter-Strike match data.
This implementation uses the PandaScore API instead of web scraping.

Usage:
    python tester_pandascore.py <team_slug>
    
Example:
    python tester_pandascore.py falcons-esports
    python tester_pandascore.py mousesports-cs-go
    python tester_pandascore.py team-vitality

Note: You need to set your PandaScore API key in the PANDASCORE_API_KEY constant below.
"""

import sys
from datetime import datetime
import requests
import arrow
from dateutil import parser as date_parser


# Set your PandaScore API key here
PANDASCORE_API_KEY = ""


def print_match_results(result: dict):
    """
    Print formatted match results to the console.
    
    Args:
        result: Match data dict with team, opponent, tournament, next_match, etc.
    """
    print(f"\n{'='*60}")
    print("MATCH DATA EXTRACTED SUCCESSFULLY")
    print(f"{'='*60}\n")
    
    print(f"🎮 Match Status: {result['match_status']}")
    print(f"📅 Match Time: {result['next_match']['start_time']}")
    
    # Use arrow for human-readable time
    kickoff_in = arrow.get(int(result['timestamp_string'])).humanize()
    clock = arrow.get(int(result['timestamp_string'])).to('local').format('h:mm A')
    print(f"   {kickoff_in} at {clock}")
    print()
    
    print(f"🏠 Your Team:")
    print(f"   Name: {result['team']['name']}")
    print(f"   Abbrev: {result['team']['abbrev']}")
    print(f"   Link: {result['team']['link']}")
    print(f"   Logo: {result['team']['logo']}")
    if result['team']['score'] is not None:
        print(f"   Score: {result['team']['score']}")
    print()
    
    print(f"🆚 Opponent:")
    print(f"   Name: {result['opponent']['name']}")
    print(f"   Abbrev: {result['opponent']['abbrev']}")
    print(f"   Link: {result['opponent']['link']}")
    print(f"   Logo: {result['opponent']['logo']}")
    if result['opponent']['score'] is not None:
        print(f"   Score: {result['opponent']['score']}")
    print()
    
    print(f"🏆 Tournament:")
    print(f"   Name: {result['tournament']['name']}")
    print(f"   Link: {result['tournament']['link']}")
    print()


def fetch_team_match(team_slug: str) -> dict:
    """
    Fetch the most recent match for a team using the PandaScore API.
    
    Args:
        team_slug: Team slug (e.g., "falcons-esports", "mousesports-cs-go")
        
    Returns:
        dict: Match data or None if not found
    """
    print(f"\n{'='*60}")
    print(f"Fetching match data for: {team_slug}")
    print(f"{'='*60}\n")
    
    # Construct API URL
    api_url = f"https://api.pandascore.co/teams/{team_slug}/matches"
    params = {
        "videogame_title": "cs-2",
        "page[size]": "1"
    }
    
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {PANDASCORE_API_KEY}"
    }
    
    print(f"✓ Using PandaScore API: {api_url}")
    print(f"✓ Parameters: {params}")
    print()
    
    try:
        # Make API request
        response = requests.get(api_url, params=params, headers=headers)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
        
        # Parse JSON response
        matches = response.json()
        
        if not matches or len(matches) == 0:
            print("❌ No matches found for this team")
            return None
        
        print(f"✓ Found {len(matches)} match(es)")
        
        # Get the first match (most recent)
        match_data = matches[0]
        
        print(f"✓ Processing match")
        print()
        
        # Extract match timestamp
        scheduled_at = match_data.get("scheduled_at") or match_data.get("begin_at")
        if not scheduled_at:
            print("❌ No scheduled_at or begin_at field in match data")
            return None
        
        # Parse ISO 8601 timestamp to datetime
        match_timestamp = date_parser.isoparse(scheduled_at)
        match_timestamp_string = str(int(match_timestamp.timestamp()))
        
        print(f"✓ Match timestamp: {match_timestamp}")
        
        # Determine match status
        api_status = match_data.get("status", "not_started")
        status_map = {
            "not_started": "PRE",
            "running": "IN",
            "finished": "POST"
        }
        match_status = status_map.get(api_status, "PRE")
        
        print(f"✓ Match status: {match_status} (API status: {api_status})")
        
        # Extract opponents
        opponents = match_data.get("opponents", [])
        
        # Handle case where opponents array is empty or has less than 2 teams
        if len(opponents) < 2:
            print(f"⚠️  Only {len(opponents)} opponent(s) listed")
            
            # Try to get at least our team
            if len(opponents) == 1:
                team_data = opponents[0].get("opponent", {})
                
                team = {
                    "abbrev": team_data.get("slug", team_data.get("acronym", team_slug)),
                    "name": team_data.get("name", "Unknown"),
                    "link": f"https://liquipedia.net/counterstrike/{team_slug}",
                    "logo": team_data.get("image_url", ""),
                    "score": None,
                }
                
                # Opponent is TBD
                opponent = {
                    "abbrev": "TBD",
                    "name": "TBD",
                    "link": "",
                    "logo": "",
                    "score": None,
                }
            else:
                # No opponents at all
                team = {
                    "abbrev": team_slug,
                    "name": team_slug.replace("-", " ").replace("_", " ").title(),
                    "link": f"https://liquipedia.net/counterstrike/{team_slug}",
                    "logo": "",
                    "score": None,
                }
                
                opponent = {
                    "abbrev": "TBD",
                    "name": "TBD",
                    "link": "",
                    "logo": "",
                    "score": None,
                }
            
            print(f"✓ Our team: {team['name']} ({team['abbrev']})")
            print(f"✓ Opponent: TBD (to be determined)")
        
        else:
            # Determine which opponent is our team
            team_data = None
            opponent_data = None
            
            for opp in opponents:
                opp_info = opp.get("opponent", {})
                opp_slug = opp_info.get("slug", "")
                
                # Try to match by slug (handle both dash and underscore variations)
                normalized_team_slug = team_slug.replace("_", "-")
                normalized_opp_slug = opp_slug.replace("_", "-")
                
                if normalized_opp_slug == normalized_team_slug:
                    team_data = opp_info
                else:
                    opponent_data = opp_info
            
            # If we couldn't match by slug, just use the first two opponents
            if not team_data or not opponent_data:
                print("⚠️  Could not match team by slug, using first opponent as team")
                team_data = opponents[0].get("opponent", {})
                opponent_data = opponents[1].get("opponent", {})
            
            # Extract scores from results array
            results = match_data.get("results", [])
            team_score = None
            opponent_score = None
            
            if results and len(results) >= 2:
                # Try to match scores to teams by team_id
                team_id = team_data.get("id")
                opponent_id = opponent_data.get("id")
                
                for result in results:
                    if result.get("team_id") == team_id:
                        team_score = result.get("score")
                    elif result.get("team_id") == opponent_id:
                        opponent_score = result.get("score")
                
                # If we couldn't match by ID, just use the order
                if team_score is None and opponent_score is None:
                    team_score = results[0].get("score")
                    opponent_score = results[1].get("score")
            
            # Extract team info
            team_slug_clean = team_data.get("slug", team_data.get("acronym", team_slug))
            team = {
                "abbrev": team_slug_clean,
                "name": team_data.get("name", "Unknown"),
                "link": f"https://liquipedia.net/counterstrike/{team_slug_clean}",
                "logo": team_data.get("image_url", ""),
                "score": team_score,
            }
            
            # Extract opponent info
            opponent_slug = opponent_data.get("slug", opponent_data.get("acronym", ""))
            opponent = {
                "abbrev": opponent_slug,
                "name": opponent_data.get("name", "Unknown"),
                "link": f"https://liquipedia.net/counterstrike/{opponent_slug}" if opponent_slug else "",
                "logo": opponent_data.get("image_url", ""),
                "score": opponent_score,
            }
            
            print(f"✓ Our team: {team['name']} ({team['abbrev']})")
            print(f"✓ Opponent: {opponent['name']} ({opponent['abbrev']})")
            if team_score is not None and opponent_score is not None:
                print(f"✓ Score: {team_score} - {opponent_score}")
        
        # Extract tournament info
        tournament_data = match_data.get("tournament", {})
        league_data = match_data.get("league", {})
        serie_data = match_data.get("serie", {})
        
        tournament_name = (
            serie_data.get("full_name") or 
            serie_data.get("name") or 
            tournament_data.get("name") or 
            league_data.get("name") or 
            "Unknown"
        )
        
        # Try to generate a Liquipedia link from the tournament slug
        tournament_slug = (
            serie_data.get("slug") or 
            tournament_data.get("slug") or 
            league_data.get("slug") or 
            ""
        )
        
        tournament_link = ""
        if tournament_slug:
            # Convert slug to potential Liquipedia format
            # Remove cs-go or cs-2 prefix if present
            clean_slug = tournament_slug.replace("cs-go-", "").replace("cs-2-", "")
            # Capitalize words
            clean_slug_parts = clean_slug.split("-")
            clean_slug_formatted = "/".join([part.capitalize() for part in clean_slug_parts])
            tournament_link = f"https://liquipedia.net/counterstrike/{clean_slug_formatted}"
        
        tournament = {
            "name": tournament_name,
            "link": tournament_link,
        }
        
        print(f"✓ Tournament: {tournament_name}")
        
        next_match = {
            "start_time": match_timestamp,
        }
        
        result = {
            "team": team,
            "opponent": opponent,
            "tournament": tournament,
            "next_match": next_match,
            "match_status": match_status,
            "timestamp_string": match_timestamp_string,
        }
        
        # Print formatted results
        print_match_results(result)
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error making API request: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"\n❌ Error parsing API response: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python tester_pandascore.py <team_slug>")
        print("\nExample:")
        print("  python tester_pandascore.py falcons-esports")
        print("  python tester_pandascore.py mousesports-cs-go")
        print("  python tester_pandascore.py team-vitality")
        print("\nNote: Make sure to set your PANDASCORE_API_KEY in the script first!")
        sys.exit(1)
    
    team_slug = sys.argv[1]
    
    result = fetch_team_match(team_slug)
    
    if result is None:
        print("\n💡 Debugging tips:")
        print("   1. Check if the team slug is correct")
        print("   2. Make sure your API key is set correctly")
        print("   3. Verify the team has matches in the PandaScore database")
        print("   4. Check if the API endpoint is accessible")
        sys.exit(1)
    
    print(f"{'='*60}")
    print("✅ SUCCESS - Match data retrieved successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
