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
from bs4 import BeautifulSoup


async def get_soup_object(link) -> BeautifulSoup:
    """Fetch the HTML from a URL and return a BeautifulSoup object."""
    async with aiohttp.ClientSession() as session, session.get(link) as response:
        html = await response.text()
        return BeautifulSoup(html, "html.parser")


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
        "view_links": livestream_list,
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


async def process_team_page_match(match_container, team_name, show_score=True):
    """
    Process a match from the team page's Upcoming Matches carousel.
    Uses the vertical match-info structure from team pages.
    
    Args:
        match_container: BeautifulSoup element for the match-info-vertical div
        team_name: Name of the team we're searching for
        show_score: Whether to extract score information
        
    Returns:
        dict: All extracted match data
    """
    print(f"✓ Processing team page match for {team_name}")
    
    # Match timestamp
    timer_span = match_container.find("span", class_="timer-object")
    if timer_span is None:
        print("❌ Could not find timer-object span")
        return None
        
    match_timestamp_string = timer_span.get("data-timestamp", "").strip()
    if not match_timestamp_string:
        print("❌ Could not find data-timestamp attribute")
        return None
        
    match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
    print(f"✓ Match timestamp: {match_timestamp}")

    # Tournament info
    tournament_section = match_container.find("div", class_="match-info-tournament")
    tournament_name = "Unknown"
    tournament_link = ""
    
    if tournament_section:
        tournament_name_section = tournament_section.find("span", class_="match-info-tournament-name")
        if tournament_name_section:
            tournament_a = tournament_name_section.find("a")
            if tournament_a:
                tournament_name = tournament_a.get("title", "Unknown").strip()
                tournament_link = tournament_a.get("href", "").strip()
    
    print(f"✓ Tournament: {tournament_name}")

    # Get teams from match-info-header-vertical
    match_info_header = match_container.find("div", class_="match-info-header-vertical")
    if not match_info_header:
        print("❌ Could not find match-info-header-vertical")
        return None

    # Find all opponent rows
    opponent_rows = match_info_header.find_all("div", class_="match-info-opponent-row")
    if len(opponent_rows) < 2:
        print(f"❌ Expected 2 opponent rows, found {len(opponent_rows)}")
        return None

    # Process first team (row 0)
    team_1_name = "Unknown"
    team_1_abbrev = "Unknown"
    team_1_link = ""
    team_1_icon_url = ""
    team_1_score = None
    
    team_1_identity = opponent_rows[0].find("div", class_="match-info-opponent-identity")
    if team_1_identity:
        block_team = team_1_identity.find("div", class_="block-team")
        if block_team:
            # Get team name
            name_span = block_team.find("span", class_="name")
            if name_span:
                team_a = name_span.find("a")
                if team_a:
                    team_1_name = team_a.text.strip()
                    team_1_link = team_a.get("href", "")
                    team_1_classes = team_a.get("class", [])
                    
                    # Check if it's a self-link first
                    if "mw-selflink" in team_1_classes or "selflink" in team_1_classes:
                        # Self-link means this is the current team's page - use team_name
                        team_1_abbrev = team_1_name
                        print(f"  Team 1 is self-link (current team)")
                    elif team_1_link:
                        # Handle different URL formats
                        if "/counterstrike/" in team_1_link and "index.php" not in team_1_link:
                            # Normal link: /counterstrike/TeamName
                            team_1_abbrev = team_1_link.split("/counterstrike/")[-1]
                        elif "title=" in team_1_link:
                            # Redlink format: /index.php?title=Phoenix_(American_team)&action=edit
                            import urllib.parse
                            params = urllib.parse.parse_qs(urllib.parse.urlparse(team_1_link).query)
                            if 'title' in params:
                                title = params['title'][0]
                                # Remove namespace if present
                                if ':' in title:
                                    team_1_abbrev = title.split(':')[-1]
                                else:
                                    team_1_abbrev = title
                                print(f"  Team 1 extracted from title param: {team_1_abbrev}")
                        else:
                            team_1_abbrev = team_1_name
                    else:
                        # No href attribute - fallback to name
                        team_1_abbrev = team_1_name
            
            # Get team logo - look for any img in block-team
            team_img = block_team.find("img")
            if team_img:
                team_1_icon_url = team_img.get("src", "")
    
    # Get score if present
    if show_score:
        score_span = opponent_rows[0].find("span", class_="match-info-opponent-score")
        if score_span and score_span.text.strip():
            team_1_score = score_span.text.strip()

    # Process second team (row 1)
    team_2_name = "Unknown"
    team_2_abbrev = "Unknown"
    team_2_link = ""
    team_2_icon_url = ""
    team_2_score = None
    
    team_2_identity = opponent_rows[1].find("div", class_="match-info-opponent-identity")
    if team_2_identity:
        block_team = team_2_identity.find("div", class_="block-team")
        if block_team:
            # Get team name
            name_span = block_team.find("span", class_="name")
            if name_span:
                team_a = name_span.find("a")
                if team_a:
                    team_2_name = team_a.text.strip()
                    team_2_link = team_a.get("href", "")
                    team_2_classes = team_a.get("class", [])
                    
                    # Check if it's a self-link first
                    if "mw-selflink" in team_2_classes or "selflink" in team_2_classes:
                        # Self-link means this is the current team's page - use team_name
                        team_2_abbrev = team_2_name
                        print(f"  Team 2 is self-link (current team)")
                    elif team_2_link:
                        # Handle different URL formats
                        if "/counterstrike/" in team_2_link and "index.php" not in team_2_link:
                            # Normal link: /counterstrike/TeamName
                            team_2_abbrev = team_2_link.split("/counterstrike/")[-1]
                        elif "title=" in team_2_link:
                            # Redlink format: /index.php?title=Phoenix_(American_team)&action=edit
                            import urllib.parse
                            params = urllib.parse.parse_qs(urllib.parse.urlparse(team_2_link).query)
                            if 'title' in params:
                                title = params['title'][0]
                                # Remove namespace if present
                                if ':' in title:
                                    team_2_abbrev = title.split(':')[-1]
                                else:
                                    team_2_abbrev = title
                                print(f"  Team 2 extracted from title param: {team_2_abbrev}")
                        else:
                            team_2_abbrev = team_2_name
                    else:
                        # No href attribute - fallback to name
                        team_2_abbrev = team_2_name
            
            # Get team logo
            team_img = block_team.find("img")
            if team_img:
                team_2_icon_url = team_img.get("src", "")
    
    # Get score if present
    if show_score:
        score_span = opponent_rows[1].find("span", class_="match-info-opponent-score")
        if score_span and score_span.text.strip():
            team_2_score = score_span.text.strip()

    print(f"✓ Team 1: {team_1_name} ({team_1_abbrev})")
    print(f"✓ Team 2: {team_2_name} ({team_2_abbrev})")

    # Determine which team is ours and which is opponent
    if team_1_abbrev == team_name:
        team = {
            "abbrev": team_1_abbrev,
            "name": team_1_name,
            "link": "https://liquipedia.net/counterstrike/" + team_name,
            "logo": "https://liquipedia.net" + team_1_icon_url if team_1_icon_url else "",
            "score": team_1_score,
        }
        opponent = {
            "abbrev": team_2_abbrev,
            "name": team_2_name,
            "link": "https://liquipedia.net" + team_2_link if team_2_link else "",
            "logo": "https://liquipedia.net" + team_2_icon_url if team_2_icon_url else "",
            "score": team_2_score,
        }
    else:
        team = {
            "abbrev": team_2_abbrev,
            "name": team_2_name,
            "link": "https://liquipedia.net/counterstrike/" + team_name,
            "logo": "https://liquipedia.net" + team_2_icon_url if team_2_icon_url else "",
            "score": team_2_score,
        }
        opponent = {
            "abbrev": team_1_abbrev,
            "name": team_1_name,
            "link": "https://liquipedia.net" + team_1_link if team_1_link else "",
            "logo": "https://liquipedia.net" + team_1_icon_url if team_1_icon_url else "",
            "score": team_1_score,
        }

    tournament = {
        "name": tournament_name,
        "link": "https://liquipedia.net" + tournament_link if tournament_link else "",
    }
    
    next_match = {
        "start_time": match_timestamp,
        "view_links": [],  # TODO: Implement stream finding for team page
    }

    # Team page upcoming matches are always PRE status
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
        # For upcoming matches, use the team page
        team_url = f"https://liquipedia.net/counterstrike/{team_name}"
        print(f"✓ Using team page: {team_url}")
        soup = await get_soup_object(team_url)
        
        # Find the carousel container
        carousel_container = soup.find("div", attrs={"data-switch-group-container": "countdown"})
        if not carousel_container:
            print("❌ Could not find countdown carousel container")
            return None
        
        print("✓ Found carousel container")
        
        # Navigate to carousel content
        carousel = carousel_container.find("div", class_="carousel")
        if not carousel:
            print("❌ Could not find carousel div")
            return None
        
        carousel_content = carousel.find("div", class_="carousel-content")
        if not carousel_content:
            print("❌ Could not find carousel-content div")
            return None
        
        print("✓ Found carousel content")
        
        # Get the first carousel item
        carousel_item = carousel_content.find("div", class_="carousel-item")
        if not carousel_item:
            print("❌ No carousel items found - team may not have upcoming matches")
            return None
        
        print("✓ Found first carousel item (match)")
        
        # Get the match-info-vertical div
        match_container = carousel_item.find("div", class_="match-info--vertical")
        if not match_container:
            print("❌ Could not find match-info--vertical div")
            return None
        
        print("✓ Found match-info--vertical container")
        
        try:
            result = await process_team_page_match(match_container, team_name)
            
            if result is None:
                return None
            
            # Print formatted results
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
            
            return result
            
        except Exception as e:
            print(f"\n❌ Error parsing team page match data: {e}")
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
