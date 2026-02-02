#!/usr/bin/env python3
"""
Standalone test script for Counter-Strike match scraping logic.
This extracts the web scraping functionality from the Home Assistant integration
to allow easy testing and debugging without HA dependencies.

Usage:
    python tester.py <team_name> [upcoming|completed]
    
Example:
    python tester.py FaZe_Clan
    python tester.py Team_Vitality upcoming
    python tester.py G2_Esports completed
"""

import asyncio
import re
import sys
from datetime import datetime

import aiohttp
import arrow
import requests
from bs4 import BeautifulSoup


async def get_soup_object(link) -> BeautifulSoup:
    """Fetch the HTML from a URL and return a BeautifulSoup object."""
    async with aiohttp.ClientSession() as session, session.get(link) as response:
        html = await response.text()
        return BeautifulSoup(html, "html.parser")


def build_liquipedia_url(path: str) -> str:
    """
    Build a full Liquipedia URL from a relative path.
    
    Args:
        path: Relative path (e.g., "/counterstrike/Team_Name")
        
    Returns:
        str: Full URL or empty string if path is empty
    """
    if not path:
        return ""
    return "https://liquipedia.net" + path


def extract_team_info_from_block(block_team, team_name: str) -> dict:
    """
    Extract team information from a block-team div element.
    Handles various URL formats including self-links and redlinks.
    
    Args:
        block_team: BeautifulSoup element with class "block-team"
        team_name: Name of the team we're tracking (for self-link detection)
        
    Returns:
        dict: Team info with keys: name, abbrev, link, icon_url
    """
    import urllib.parse
    
    team_info = {
        "name": "Unknown",
        "abbrev": "Unknown",
        "link": "",
        "icon_url": "",
    }
    
    if not block_team:
        return team_info
    
    # Get team name and link
    name_span = block_team.find("span", class_="name")
    if name_span:
        team_a = name_span.find("a")
        if team_a:
            team_info["name"] = team_a.text.strip()
            team_link = team_a.get("href", "")
            team_classes = team_a.get("class", [])
            
            # Check if it's a self-link first
            if "mw-selflink" in team_classes or "selflink" in team_classes:
                # Self-link means this is the current team's page
                team_info["abbrev"] = team_info["name"]
                print(f"  Detected self-link (current team)")
            elif team_link:
                team_info["link"] = team_link
                # Handle different URL formats
                if "/counterstrike/" in team_link and "index.php" not in team_link:
                    # Normal link: /counterstrike/TeamName
                    team_info["abbrev"] = team_link.split("/counterstrike/")[-1]
                elif "title=" in team_link:
                    # Redlink format: /index.php?title=Phoenix_(American_team)&action=edit
                    params = urllib.parse.parse_qs(urllib.parse.urlparse(team_link).query)
                    if 'title' in params:
                        title = params['title'][0]
                        # Remove namespace if present
                        if ':' in title:
                            team_info["abbrev"] = title.split(':')[-1]
                        else:
                            team_info["abbrev"] = title
                        print(f"  Extracted from title param: {team_info['abbrev']}")
                else:
                    team_info["abbrev"] = team_info["name"]
            else:
                # No href attribute - fallback to name
                team_info["abbrev"] = team_info["name"]
    
    # Get team logo
    team_img = block_team.find("img")
    if team_img:
        team_info["icon_url"] = team_img.get("src", "")
    
    return team_info


def determine_team_and_opponent(team_1_info: dict, team_2_info: dict, 
                                 team_name: str, team_1_score=None, team_2_score=None) -> tuple:
    """
    Determine which team is the user's team and which is the opponent.
    
    Args:
        team_1_info: Dict with keys: name, abbrev, link, icon_url
        team_2_info: Dict with keys: name, abbrev, link, icon_url
        team_name: The team abbreviation we're tracking
        team_1_score: Optional score for team 1
        team_2_score: Optional score for team 2
        
    Returns:
        tuple: (team_dict, opponent_dict) with full structure including scores
    """
    if team_1_info["abbrev"] == team_name:
        team = {
            "abbrev": team_1_info["abbrev"],
            "name": team_1_info["name"],
            "link": f"https://liquipedia.net/counterstrike/{team_name}",
            "logo": build_liquipedia_url(team_1_info["icon_url"]),
            "score": team_1_score,
        }
        opponent = {
            "abbrev": team_2_info["abbrev"],
            "name": team_2_info["name"],
            "link": build_liquipedia_url(team_2_info["link"]),
            "logo": build_liquipedia_url(team_2_info["icon_url"]),
            "score": team_2_score,
        }
    else:
        team = {
            "abbrev": team_2_info["abbrev"],
            "name": team_2_info["name"],
            "link": f"https://liquipedia.net/counterstrike/{team_name}",
            "logo": build_liquipedia_url(team_2_info["icon_url"]),
            "score": team_2_score,
        }
        opponent = {
            "abbrev": team_1_info["abbrev"],
            "name": team_1_info["name"],
            "link": build_liquipedia_url(team_1_info["link"]),
            "logo": build_liquipedia_url(team_1_info["icon_url"]),
            "score": team_1_score,
        }
    
    return team, opponent


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


async def process_match(team_link, team_name, show_score=True):
    """
    Process a single match and extract all relevant data.
    
    Args:
        team_link: BeautifulSoup element for the team link
        team_name: Name of the team we're searching for
        show_score: Whether to extract score information
        
    Returns:
        dict: All extracted match data
    """
    match_status = "NOT_FOUND"
    href_to_search = team_name

    # Navigate up the DOM tree to find the match container (new div-based structure)
    # Path: a -> span -> div.block-team -> div.match-info-header-opponent -> 
    #       div.match-info-header -> div.match-info -> div.new-match-style
    current = team_link
    team_match = None
    
    for _ in range(10):
        if current is None:
            break
        if hasattr(current, 'name') and current.name == 'div':
            classes = current.get('class', [])
            if 'new-match-style' in classes:
                team_match = current
                break
        current = current.parent
    
    if team_match is None:
        print("❌ Could not find match container (new-match-style div)")
        return None

    # Match timestamp
    timer_span = team_match.find("span", class_="timer-object")
    if timer_span is None:
        print("❌ Could not find timer-object span")
        return None
        
    match_timestamp_string = timer_span.get("data-timestamp", "").strip()
    if not match_timestamp_string:
        print("❌ Could not find data-timestamp attribute")
        return None
        
    match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
    print(f"✓ Match timestamp: {match_timestamp}")

    # Get match info header to access teams and score
    match_info_header = team_match.find("div", class_="match-info-header")
    if not match_info_header:
        print("❌ Could not find match-info-header")
        return None

    # Check for versus/score section to determine match status
    score_holder = match_info_header.find("div", class_="match-info-header-scoreholder")
    match_status = "PRE"  # Default to upcoming
    
    if score_holder:
        score_text = score_holder.text.strip()
        if "vs" in score_text.lower():
            match_status = "PRE"
        elif ":" in score_text:
            match_status = "POST"
        else:
            match_status = "IN"
    
    # Check for winner classes on the match container
    match_classes = team_match.get("class", [])
    if "winner-left" in match_classes or "winner-right" in match_classes:
        match_status = "POST"
    
    print(f"✓ Match status: {match_status}")

    # Extract scores if match is POST or IN and show_score is true
    team_left_score = None
    team_right_score = None
    if show_score and match_status in ("POST", "IN") and score_holder:
        score_upper = score_holder.find("span", class_="match-info-header-scoreholder-upper")
        if score_upper and ":" in score_upper.text:
            score_parts = score_upper.text.split(":")
            team_left_score = score_parts[0].strip()
            team_right_score = score_parts[1].strip()
            print(f"✓ Score: {team_left_score}:{team_right_score}")

    # Team and Opponent info (new div structure)
    # Left team
    team_left_opponent = match_info_header.find("div", class_="match-info-header-opponent-left")
    if not team_left_opponent:
        # Try without -left suffix for completed matches
        team_left_opponent = match_info_header.find("div", class_="match-info-header-opponent")
    
    team_left_name = "Unknown"
    team_left_abbrev = "Unknown"
    team_left_link = ""
    team_left_icon_url = ""
    
    if team_left_opponent:
        team_left_block = team_left_opponent.find("div", class_="block-team")
        if team_left_block:
            # Get team name from the <span class="name"> section
            name_span = team_left_block.find("span", class_="name")
            if name_span:
                team_left_a = name_span.find("a")
                if team_left_a:
                    team_left_name = team_left_a.text.strip()
                    team_left_link = team_left_a.get("href", "")
                    team_left_abbrev = team_left_link.split("/")[-1] if team_left_link else "Unknown"
            
            # Get team logo
            team_left_img = team_left_block.find("img")
            if team_left_img:
                team_left_icon_url = team_left_img.get("src", "")

    # Right team
    # Find all opponents and get the one that's not the left one
    all_opponents = match_info_header.find_all("div", class_="match-info-header-opponent")
    team_right_opponent = None
    
    for opponent in all_opponents:
        if opponent != team_left_opponent:
            team_right_opponent = opponent
            break
    
    team_right_name = "Unknown"
    team_right_abbrev = "Unknown"
    team_right_link = ""
    team_right_icon_url = ""
    
    if team_right_opponent:
        team_right_block = team_right_opponent.find("div", class_="block-team")
        if team_right_block:
            name_span = team_right_block.find("span", class_="name")
            if name_span:
                team_right_a = name_span.find("a")
                if team_right_a:
                    team_right_name = team_right_a.text.strip()
                    team_right_link = team_right_a.get("href", "")
                    team_right_abbrev = team_right_link.split("/")[-1] if team_right_link else "Unknown"
            
            team_right_img = team_right_block.find("img")
            if team_right_img:
                team_right_icon_url = team_right_img.get("src", "")
    
    # Handle TBD opponent
    if not team_right_name or team_right_name == "TBD":
        team_right_name = "TBD"
        team_right_link = team_left_link
        team_right_abbrev = "TBD"
        team_right_icon_url = "/commons/images/thumb/5/57/Counter-Strike_2_default_lightmode.png/47px-Counter-Strike_2_default_lightmode.png"

    print(f"✓ Left team: {team_left_name} ({team_left_abbrev})")
    print(f"✓ Right team: {team_right_name} ({team_right_abbrev})")

    # Tournament name and link (new structure)
    tournament_section = team_match.find("div", class_="match-info-tournament")
    tournament_name = "Unknown"
    tournament_link = ""
    
    if tournament_section:
        tournament_link_section = tournament_section.find("span", class_="league-icon-small-image")
        if tournament_link_section:
            tournament_a = tournament_link_section.find("a")
            if tournament_a:
                tournament_name = tournament_a.get("title", "Unknown").strip()
                tournament_link = tournament_a.get("href", "").strip()
    
    print(f"✓ Tournament: {tournament_name}")

    # Determine which side is our team
    if team_left_abbrev == team_name:
        team = {
            "abbrev": team_left_abbrev,
            "name": team_left_name,
            "link": "https://liquipedia.net/counterstrike/" + href_to_search,
            "logo": "https://liquipedia.net" + team_left_icon_url if team_left_icon_url else "",
            "score": team_left_score,
        }
        opponent = {
            "abbrev": team_right_abbrev,
            "name": team_right_name,
            "link": "https://liquipedia.net" + team_right_link if team_right_link else "",
            "logo": "https://liquipedia.net" + team_right_icon_url if team_right_icon_url else "",
            "score": team_right_score,
        }
    else:
        team = {
            "abbrev": team_right_abbrev,
            "name": team_right_name,
            "link": "https://liquipedia.net/counterstrike/" + href_to_search,
            "logo": "https://liquipedia.net" + team_right_icon_url if team_right_icon_url else "",
            "score": team_right_score,
        }
        opponent = {
            "abbrev": team_left_abbrev,
            "name": team_left_name,
            "link": "https://liquipedia.net" + team_left_link if team_left_link else "",
            "logo": "https://liquipedia.net" + team_left_icon_url if team_left_icon_url else "",
            "score": team_left_score,
        }

    tournament = {
        "name": tournament_name,
        "link": "https://liquipedia.net" + tournament_link if tournament_link else "",
    }
    
    next_match = {
        "start_time": match_timestamp,
    }

    # Adjust match status (IN looks ugly, so show as PRE)
    if match_status == "IN":
        match_status = "PRE"

    return {
        "team": team,
        "opponent": opponent,
        "tournament": tournament,
        "next_match": next_match,
        "match_status": match_status,
        "timestamp_string": match_timestamp_string,
    }

async def process_matches_page_match(soup, team_name):
    """
    Process the most recent completed match from the team's /Matches page.
    
    Args:
        soup: BeautifulSoup object of the team's Matches page
        team_name: Name of the team we're searching for
        
    Returns:
        dict: All extracted match data for the most recent completed match
    """
    print(f"✓ Processing matches page for {team_name}")
    
    # The matches table is typically in div.mw-parser-output
    content = soup.find("div", class_="mw-parser-output")
    if not content:
        print("❌ Could not find mw-parser-output div")
        return None
    
    # Find all match rows in the table
    # Matches are in table rows with specific structure
    match_rows = content.find_all("tr")
    
    # Find the first completed match (has a score with ":")
    for row in match_rows:
        # Get all cells in the row
        cells = row.find_all("td", recursive=False)
        
        # Need at least 9 cells for a proper match row
        # Structure: Date, Tier, Type, (empty), (empty), Tournament, Participant, Score, Opponent
        if len(cells) < 9:
            continue
        
        # The score is at index 7
        score_cell = cells[7]
        
        # Get the score text
        score_content = score_cell.find_all(string=True, recursive=True)
        score_text = "".join(score_content).strip()
        
        # Look for a real score (not "W : FF" or upcoming matches with "vs")
        if ":" in score_text and "vs" not in score_text.lower():
            # Check if this is a real numeric score
            parts = score_text.split(":")
            if len(parts) == 2:
                left_score = parts[0].strip()
                right_score = parts[1].strip()
                
                # Skip forfeits, walkover, or dates
                if "FF" in left_score or "FF" in right_score or "W" in left_score:
                    continue
                if "-" in left_score or "EST" in score_text or "PST" in score_text:
                    continue
                
                # Try to verify these are numeric scores
                try:
                    int(left_score)
                    int(right_score)
                except ValueError:
                    # Not numeric scores, skip
                    continue
                
                print(f"✓ Found completed match with score: {score_text}")
                
                # Cell structure: Date, Tier, Type, (empty), (empty), Tournament, Participant, Score, Opponent
                date_cell = cells[0]
                tournament_cell = cells[5]
                participant_cell = cells[6]
                score_cell = cells[7]
                opponent_cell = cells[8]
                
                # Extract date/timestamp
                timer_span = date_cell.find("span", class_="timer-object")
                if not timer_span:
                    print("❌ Could not find timer-object in date cell")
                    continue
                
                match_timestamp_string = timer_span.get("data-timestamp", "").strip()
                if not match_timestamp_string:
                    print("❌ No timestamp found")
                    continue
                
                match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
                print(f"✓ Match timestamp: {match_timestamp}")
                
                # Extract tournament
                tournament_name = "Unknown"
                tournament_link = ""
                tournament_a = tournament_cell.find("a")
                if tournament_a:
                    tournament_name = tournament_a.get("title", tournament_a.text.strip())
                    tournament_link = tournament_a.get("href", "")
                
                print(f"✓ Tournament: {tournament_name}")
                
                # Extract our team info
                team_name_display = "Unknown"
                team_abbrev = team_name
                team_logo = ""
                
                team_img = participant_cell.find("img")
                if team_img:
                    team_logo = team_img.get("src", "")
                
                # Try to find team name - could be in various places
                team_link_elem = participant_cell.find("a", href=True)
                if team_link_elem:
                    team_name_display = team_link_elem.text.strip()
                
                # If team name is still empty, try getting all text from the cell
                if not team_name_display or team_name_display == "Unknown":
                    cell_text = participant_cell.get_text(strip=True)
                    # Remove any whitespace and extract team name
                    if cell_text:
                        team_name_display = cell_text
                
                # Last resort: use the team parameter
                if not team_name_display or team_name_display == "Unknown":
                    team_name_display = team_name
                
                # Extract opponent info
                opponent_name = "Unknown"
                opponent_abbrev = "Unknown"
                opponent_link = ""
                opponent_logo = ""
                
                opponent_img = opponent_cell.find("img")
                if opponent_img:
                    opponent_logo = opponent_img.get("src", "")
                
                # Try to find opponent name
                opponent_link_elem = opponent_cell.find("a", href=True)
                if opponent_link_elem:
                    opponent_name = opponent_link_elem.text.strip()
                    opponent_link = opponent_link_elem.get("href", "")
                    if "/counterstrike/" in opponent_link:
                        opponent_abbrev = opponent_link.split("/counterstrike/")[-1]
                    else:
                        opponent_abbrev = opponent_name
                
                # If opponent name is still empty, try getting all text from the cell
                if not opponent_name or opponent_name == "Unknown":
                    cell_text = opponent_cell.get_text(strip=True)
                    if cell_text:
                        opponent_name = cell_text
                        opponent_abbrev = cell_text
                
                print(f"✓ Our team: {team_name_display}")
                print(f"✓ Opponent: {opponent_name} ({opponent_abbrev})")
                print(f"✓ Score: {left_score} : {right_score}")
                
                # Build result structure
                team = {
                    "abbrev": team_abbrev,
                    "name": team_name_display,
                    "link": f"https://liquipedia.net/counterstrike/{team_name}",
                    "logo": "https://liquipedia.net" + team_logo if team_logo else "",
                    "score": left_score,
                }
                
                opponent = {
                    "abbrev": opponent_abbrev,
                    "name": opponent_name,
                    "link": "https://liquipedia.net" + opponent_link if opponent_link else "",
                    "logo": "https://liquipedia.net" + opponent_logo if opponent_logo else "",
                    "score": right_score,
                }
                
                tournament = {
                    "name": tournament_name,
                    "link": "https://liquipedia.net" + tournament_link if tournament_link else "",
                }
                
                next_match = {
                    "start_time": match_timestamp,
                }
                
                return {
                    "team": team,
                    "opponent": opponent,
                    "tournament": tournament,
                    "next_match": next_match,
                    "match_status": "POST",
                    "timestamp_string": match_timestamp_string,
                }
    
    print("❌ No completed matches found on Matches page")
    return None


async def scrape_team_match(team_name: str, match_type: str = "upcoming"):
    """
    Scrape match data for a given team.
    
    Args:
        team_name: The team abbreviation/name to search for
        match_type: Either "upcoming" (default) or "completed"
        
    Returns:
        dict: Match data including team, opponent, tournament, and next match info
    """
    print(f"\n{'='*60}")
    print(f"Fetching {match_type} match data for: {team_name}")
    print(f"{'='*60}\n")
    
    # Use different sources based on match type
    if match_type == "upcoming":
        # For upcoming matches, use PandaScore API
        api_url = f"https://api.pandascore.co/teams/{team_name}/matches"
        params = {
            "videogame_title": "cs-2",
            "filter[status]": "not_started"
        }
        
        # TODO: API key should be added here - will be configured later
        headers = {
            "accept": "application/json",
            "authorization": "Bearer [APIKEY]"  # Placeholder for API key
        }
        
        print(f"✓ Using PandaScore API: {api_url}")
        print(f"✓ Parameters: {params}")
        
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
                print("❌ No upcoming matches found for this team")
                return None
            
            print(f"✓ Found {len(matches)} upcoming match(es)")
            
            # Get the first upcoming match
            match_data = matches[0]
            
            print(f"✓ Processing first upcoming match")
            
            # Extract match timestamp
            scheduled_at = match_data.get("scheduled_at") or match_data.get("begin_at")
            if not scheduled_at:
                print("❌ No scheduled_at or begin_at field in match data")
                return None
            
            # Parse ISO 8601 timestamp to datetime
            from dateutil import parser as date_parser
            match_timestamp = date_parser.isoparse(scheduled_at)
            match_timestamp_string = str(int(match_timestamp.timestamp()))
            
            print(f"✓ Match timestamp: {match_timestamp}")
            
            # Extract opponents
            opponents = match_data.get("opponents", [])
            
            # Handle case where opponents array is empty (TBD teams)
            if len(opponents) == 0:
                print("⚠️  No opponents listed - teams are TBD")
                
                # Try to parse team names from match name if available
                match_name = match_data.get("name", "")
                
                # Extract team info with placeholder
                team = {
                    "abbrev": team_name,
                    "name": team_name.replace("_", " ").replace("-", " "),
                    "link": f"https://liquipedia.net/counterstrike/{team_name}",
                    "logo": "",
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
                
                print(f"✓ Our team: {team['name']} ({team['abbrev']})")
                print(f"✓ Opponent: TBD (to be determined)")
            
            elif len(opponents) < 2:
                print(f"❌ Expected 2 opponents, found {len(opponents)}")
                return None
            
            else:
                # Determine which opponent is our team
                team_data = None
                opponent_data = None
                
                for opp in opponents:
                    opp_info = opp.get("opponent", {})
                    opp_slug = opp_info.get("slug", "")
                    
                    # Try to match by slug
                    if opp_slug == team_name or opp_slug.replace("-", "_") == team_name:
                        team_data = opp_info
                    else:
                        opponent_data = opp_info
                
                # If we couldn't match by slug, just use the first two opponents
                if not team_data or not opponent_data:
                    team_data = opponents[0].get("opponent", {})
                    opponent_data = opponents[1].get("opponent", {})
                
                # Extract team info
                team = {
                    "abbrev": team_data.get("slug", team_data.get("acronym", team_name)),
                    "name": team_data.get("name", "Unknown"),
                    "link": f"https://liquipedia.net/counterstrike/{team_name}",
                    "logo": team_data.get("image_url", ""),
                    "score": None,
                }
                
                # Extract opponent info
                opponent_slug = opponent_data.get("slug", opponent_data.get("acronym", ""))
                opponent = {
                    "abbrev": opponent_slug,
                    "name": opponent_data.get("name", "Unknown"),
                    "link": f"https://liquipedia.net/counterstrike/{opponent_slug}" if opponent_slug else "",
                    "logo": opponent_data.get("image_url", ""),
                    "score": None,
                }
                
                print(f"✓ Our team: {team['name']} ({team['abbrev']})")
                print(f"✓ Opponent: {opponent['name']} ({opponent['abbrev']})")
            
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
            
            tournament = {
                "name": tournament_name,
                "link": tournament_data.get("url", ""),
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
                "match_status": "PRE",
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
    
    else:
        # For completed matches, use the team's /Matches page
        matches_url = f"https://liquipedia.net/counterstrike/{team_name}/Matches"
        print(f"✓ Using team Matches page: {matches_url}")
        soup = await get_soup_object(matches_url)
        
        try:
            result = await process_matches_page_match(soup, team_name)
            
            if result is None:
                return None
            
            # Print formatted results
            print_match_results(result)
            
            return result
            
        except Exception as e:
            print(f"\n❌ Error parsing matches page match data: {e}")
            import traceback
            traceback.print_exc()
            return None

async def main():
    if len(sys.argv) < 2:
        print("Usage: python tester.py <team_name> [upcoming|completed]")
        print("\nExample:")
        print("  python tester.py FaZe_Clan")
        print("  python tester.py Team_Vitality upcoming")
        print("  python tester.py G2_Esports completed")
        sys.exit(1)
    
    team_name = sys.argv[1]
    match_type = sys.argv[2] if len(sys.argv) > 2 else "upcoming"
    
    if match_type not in ["upcoming", "completed"]:
        print(f"Error: match_type must be 'upcoming', 'completed', got '{match_type}'")
        sys.exit(1)
    
    result = await scrape_team_match(team_name, match_type)
    
    if result is None:
        print("\n💡 Debugging tips:")
        print("   1. Check if the team name is correct (case-sensitive)")
        print("   2. Make sure the team has matches in the selected category")
        print("   3. The HTML structure may have changed - update the scraping logic")
        sys.exit(1)
    
    print(f"{'='*60}")
    print("✅ SUCCESS - Match data retrieved successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
