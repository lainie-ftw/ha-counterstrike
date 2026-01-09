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


LIQUIPEDIA = "https://liquipedia.net/counterstrike/Liquipedia:Matches"


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

    # Tournament livestream(s)
    livestream_list = []
    
    # Look for streams in the new match-info-streams section
    streams_section = team_match.find("div", class_="match-info-streams")
    
    if match_status == "POST":
        # Get completed match VOD link
        if tournament_section:
            done_livestream = tournament_section.find(title=re.compile("Watch Game"))
            if done_livestream is not None and done_livestream.find("a"):
                link_id = done_livestream.a["href"].split("/")[-1]
                if "?" in link_id:
                    link_id = link_id.split("?")[0]
                add_stream = {
                    "platform": "YouTube",
                    "id": link_id,
                    "name": "Watch Match",
                }
                livestream_list.append(add_stream)
                print(f"✓ Found VOD: {link_id}")
    else:
        # Get live/upcoming stream links
        tournament_livestreams_yt = None
        if tournament_section:
            tournament_livestreams_yt = tournament_section.find(href=re.compile("youtube"))
        if streams_section and not tournament_livestreams_yt:
            tournament_livestreams_yt = streams_section.find(href=re.compile("youtube"))
            
        if tournament_livestreams_yt is not None:
            livestream_yt_link = "https://liquipedia.net" + tournament_livestreams_yt["href"]
            print(f"✓ Fetching livestream info from: {livestream_yt_link}")
            
            livestream_soup = await get_soup_object(livestream_yt_link)
            content = livestream_soup.find("div", id="mw-content-text")

            # If there's only one stream, it'll be playing in an iframe
            parse_livestream = content.find("iframe", id="stream")
            if parse_livestream is not None:
                # link format is https://www.youtube.com/embed/{videoID}?autoplay=1
                youtube_link_pieces = parse_livestream["src"].split("/")
                video_id = (youtube_link_pieces[-1].split("?"))[0]
                stream_text = "Stream"
                add_stream = {
                    "platform": "YouTube",
                    "id": video_id,
                    "name": stream_text,
                }
                livestream_list.append(add_stream)
                print(f"  - Found stream: {stream_text} ({video_id})")
            else:
                # If there are multiple streams, they're in a ul
                parse_livestream_list = content.find("ul")
                if parse_livestream_list is not None:
                    youtube_links = parse_livestream_list.find_all(href=re.compile("youtube"))
                    for link in youtube_links:
                        link_pieces = link["href"].split("/")
                        video_id = link_pieces[-1]
                        stream_text = link.text
                        add_stream = {
                            "platform": "YouTube",
                            "id": video_id,
                            "name": stream_text,
                        }
                        livestream_list.append(add_stream)
                        print(f"  - Found stream: {stream_text} ({video_id})")

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
    
    soup = await get_soup_object(LIQUIPEDIA)
    
    # Determine which section to search in
    match_state = "1" if match_type == "upcoming" else "2"
    
    href_to_search = "/counterstrike/" + team_name
    team_link_all = soup.find_all(href=href_to_search)
    
    if not team_link_all:
        print(f"❌ No matches found for team: {team_name}")
        print(f"   Search href: {href_to_search}")
        print("\nTip: Make sure you're using the team abbreviation as it appears in Liquipedia URLs")
        return None
    
    print(f"✓ Found {len(team_link_all)} total team link(s)")
    
    # Find the specific match section (upcoming or completed)
    find_matches = soup.find("div", attrs={"data-toggle-area-content": match_state})
    if find_matches is None:
        print(f"❌ Could not find match section for type: {match_type}")
        return None
    
    print(f"✓ Found {match_type} matches section")
    
    team_find_match = find_matches.find(href=href_to_search)
    if team_find_match is None:
        print(f"❌ No {match_type} match found for team: {team_name}")
        return None
    
    print(f"✓ Found team link in {match_type} section")
    
    try:
        result = await process_match(team_find_match, team_name)
        
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
        
        if result['next_match']['view_links']:
            print(f"📺 Streams/VODs:")
            for stream in result['next_match']['view_links']:
                print(f"   - {stream['name']}: https://youtube.com/watch?v={stream['id']}")
            print()
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error parsing match data: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_scraper.py <team_name> [upcoming|completed]")
        print("\nExample:")
        print("  python test_scraper.py FaZe_Clan")
        print("  python test_scraper.py Team_Vitality upcoming")
        print("  python test_scraper.py G2_Esports completed")
        sys.exit(1)
    
    team_name = sys.argv[1]
    match_type = sys.argv[2] if len(sys.argv) > 2 else "upcoming"
    
    if match_type not in ["upcoming", "completed"]:
        print(f"Error: match_type must be 'upcoming' or 'completed', got '{match_type}'")
        sys.exit(1)
    
    result = await scrape_team_match(team_name, match_type)
    
    if result is None:
        print("\n💡 Debugging tips:")
        print("   1. Check if the team name is correct (case-sensitive)")
        print("   2. Make sure the team has matches in the selected category")
        print("   3. Visit the Liquipedia page to see current matches:")
        print(f"      {LIQUIPEDIA}")
        print("   4. The HTML structure may have changed - update the scraping logic")
        sys.exit(1)
    
    print(f"{'='*60}")
    print("✅ SUCCESS - Match data retrieved successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
