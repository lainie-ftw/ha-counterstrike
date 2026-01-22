import asyncio
from datetime import datetime, timedelta
import logging
import re

import aiohttp
from bs4 import BeautifulSoup
import arrow

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "counterstrike"
CONF_COUNTERSTRIKE = "counterstrike"

SCAN_INTERVAL = timedelta(seconds=3600)

# Data in attributes:
# team: abbrev, name, link, logo
# opponent: abbrev, name, link, logo
# tournament: name, link
# match: start time, view link

#LIQUIPEDIA = "https://liquipedia.net/counterstrike/Liquipedia:Matches"


async def get_soup_object(link) -> BeautifulSoup:
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


async def async_setup(hass: HomeAssistant, config: ConfigType):
    devices = []

    teams = config[DOMAIN]

    for team_to_process in teams:
        team = team_to_process["team"]
        show_score = team_to_process["show_score"]
        devices.append(CounterstrikeEntity(team, show_score, "upcoming", hass))
        devices.append(CounterstrikeEntity(team, show_score, "completed", hass))

    # Set up component
    component = EntityComponent(_LOGGER, DOMAIN, hass)
    await component.async_add_entities(devices)

    # Update state
    tasks = [asyncio.create_task(device.update_data()) for device in devices]
    await asyncio.wait(tasks)

    # async_track_time_interval(hass, self.update_data(), timedelta(minutes=5))

    _LOGGER.info(devices)

    return True


class CounterstrikeEntity(Entity):
    _attr_should_poll = True

    def __init__(self, input_team, show_score, upcoming_or_concluded, hass):
        team_id = input_team + "_" + upcoming_or_concluded
        self._unique_id = slugify(team_id)
        self._name = team_id
        self._team_name = input_team
        self._team = None
        self._opponent = None
        self._tournament = None
        self._next_match = None

        self._state = "NOT_FOUND"
        self._extra_state_attributes = None

        self._match_state = upcoming_or_concluded

        self._show_score = show_score
        self.hass = hass

    async def process_team_page_match(self, match_container):
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

        # Match timestamp
        timer_span = match_container.find("span", class_="timer-object")
        match_timestamp_string = timer_span.get("data-timestamp", "").strip()
        match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))

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

        # Get teams from match-info-header-vertical
        match_info_header = match_container.find("div", class_="match-info-header-vertical")

        # Find all opponent rows
        opponent_rows = match_info_header.find_all("div", class_="match-info-opponent-row")

        # Process first team (row 0)
        team_1_score = None
        team_1_identity = opponent_rows[0].find("div", class_="match-info-opponent-identity")
        block_team_1 = team_1_identity.find("div", class_="block-team") if team_1_identity else None
        team_1_info = extract_team_info_from_block(block_team_1, self._team_name)

        # Get score if present
        if self._show_score:
            score_span = opponent_rows[0].find("span", class_="match-info-opponent-score")
            if score_span and score_span.text.strip():
                team_1_score = score_span.text.strip()

        # Process second team (row 1)
        team_2_score = None
        team_2_identity = opponent_rows[1].find("div", class_="match-info-opponent-identity")
        block_team_2 = team_2_identity.find("div", class_="block-team") if team_2_identity else None
        team_2_info = extract_team_info_from_block(block_team_2, self._team_name)

        # Get score if present
        if self._show_score:
            score_span = opponent_rows[1].find("span", class_="match-info-opponent-score")
            if score_span and score_span.text.strip():
                team_2_score = score_span.text.strip()

        # Determine which team is ours and which is opponent
        team, opponent = determine_team_and_opponent(
            team_1_info, team_2_info, self._team_name, team_1_score, team_2_score
        )

        if team is None or opponent is None:
            return None

        tournament = {
            "name": tournament_name,
            "link": "https://liquipedia.net" + tournament_link if tournament_link else "",
        }

        next_match = {
            "start_time": match_timestamp,
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


    async def process_matches_page_match(self, soup):
        """
        Process the most recent completed match from the team's /Matches page.

        Args:
            soup: BeautifulSoup object of the team's Matches page
            team_name: Name of the team we're searching for

        Returns:
            dict: All extracted match data for the most recent completed match
        """

        # The matches table is typically in div.mw-parser-output
        content = soup.find("div", class_="mw-parser-output")

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
                    left_score = ""
                    right_score = ""
                    if self._show_score:
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

                    # Cell structure: Date, Tier, Type, (empty), (empty), Tournament, Participant, Score, Opponent
                    date_cell = cells[0]
                    tournament_cell = cells[5]
                    participant_cell = cells[6]
                    score_cell = cells[7]
                    opponent_cell = cells[8]

                    # Extract date/timestamp
                    timer_span = date_cell.find("span", class_="timer-object")
                    match_timestamp_string = timer_span.get("data-timestamp", "").strip()
                    match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))

                    # Extract tournament
                    tournament_name = "Unknown"
                    tournament_link = ""
                    tournament_a = tournament_cell.find("a")
                    if tournament_a:
                        tournament_name = tournament_a.get("title", tournament_a.text.strip())
                        tournament_link = tournament_a.get("href", "")

                    # Extract our team info
                    team_name_display = "Unknown"
                    team_abbrev = self._team_name
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
                        team_name_display = self._team_name

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

                    # Build result structure
                    team = {
                        "abbrev": team_abbrev,
                        "name": team_name_display,
                        "link": f"https://liquipedia.net/counterstrike/{self._team_name}",
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
        return None

    @property
    def team_name(self):
        return self._team_name

    @property
    def match_state(self):
        return self._match_state

    @property
    def show_score(self):
        return self._show_score

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def team(self):
        return self._team

    @property
    def opponent(self):
        return self._opponent

    @property
    def tournament(self):
        return self._tournament

    @property
    def next_match(self):
        return self._next_match

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._extra_state_attributes

    async def update_data(self, *_):
    # Use different sources based on match type
        _LOGGER.info("In update_data for %s - %s", self._team_name, self._match_state)
        if self._match_state == "upcoming":
            # For upcoming matches, use the team page
            team_url = f"https://liquipedia.net/counterstrike/{self._team_name}"
            soup = await get_soup_object(team_url)
            _LOGGER.info("Fetched team page for %s", self._team_name)

            # Find the carousel container
            carousel_container = soup.find("div", attrs={"data-switch-group-container": "countdown"})
            if not carousel_container:
                _LOGGER.info("Could not find carousel container for team %s", self._team_name)
                self._state = "NOT_FOUND"
                self._extra_state_attributes = {
                    "last_update": datetime.now(),
                }
                return

            # Navigate to carousel content
            carousel = carousel_container.find("div", class_="carousel")
            if not carousel:
                _LOGGER.info("Could not find carousel element for team %s", self._team_name)
                self._state = "NOT_FOUND"
                self._extra_state_attributes = {
                    "last_update": datetime.now(),
                }
                return

            carousel_content = carousel.find("div", class_="carousel-content")
            if not carousel_content:
                _LOGGER.info("Could not find carousel content for team %s", self._team_name)
                self._state = "NOT_FOUND"
                self._extra_state_attributes = {
                    "last_update": datetime.now(),
                }
                return

            # Get all carousel items and find the first future match
            carousel_items = carousel_content.find_all("div", class_="carousel-item")

            # Find the first match that is in the future
            match_container = None
            current_time = datetime.now()

            for idx, carousel_item in enumerate(carousel_items):
                # Get the match-info-vertical div
                temp_container = carousel_item.find("div", class_="match-info--vertical")
                if not temp_container:
                    continue

                # Check the timestamp
                timer_span = temp_container.find("span", class_="timer-object")
                if timer_span:
                    match_timestamp_string = timer_span.get("data-timestamp", "").strip()
                    if match_timestamp_string:
                        match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
                        if match_timestamp > current_time:
                            match_container = temp_container
                            break

            try:
                result = await self.process_team_page_match(match_container)

            except Exception as e:
                _LOGGER.info(f"Error parsing matches page match data: {e}")
                self._state = "NOT_FOUND"
                self._extra_state_attributes = {
                    "last_update": datetime.now(),
                }

        else:
            # For completed matches, use the team's /Matches page
            matches_url = f"https://liquipedia.net/counterstrike/{self._team_name}/Matches"
            soup = await get_soup_object(matches_url)

            try:
                result = await self.process_matches_page_match(soup)

            except Exception as e:
                _LOGGER.info(f"Error parsing matches page match data: {e}")
                self._state = "NOT_FOUND"
                self._extra_state_attributes = {
                    "last_update": datetime.now(),
                }

        if result is None:
            self._state = "NOT_FOUND"
            self._extra_state_attributes = {
                "last_update": datetime.now(),
            }
        else:
            self._state = result["match_status"]
            self._team = result["team"]
            self._opponent = result["opponent"]
            self._tournament = result["tournament"]
            self._next_match = result["next_match"]
            match_timestamp_string = result["timestamp_string"]
            self._extra_state_attributes = {
                "team_logo": self._team["logo"],
                "team_name": self._team["name"],
                "team_url": self._team["link"],
                "team_score": self._team["score"],
                "opponent_logo": self._opponent["logo"],
                "opponent_name": self._opponent["name"],
                "opponent_url": self._opponent["link"],
                "opponent_score": self._opponent["score"],
                "date": self._next_match["start_time"],
                "event_name": self._tournament["name"],
                "event_url": self._tournament["link"],
                "venue": self._tournament["name"],
                "kickoff_in": arrow.get(int(match_timestamp_string)).humanize(),
                "clock": arrow.get(int(match_timestamp_string))
                .to("local")
                .format("h:mm A"),
                "last_update": datetime.now(),
            }

        update_text = (
            "Updated data for "
            + self._team_name
            + " and match state "
            + self._match_state
        )
        _LOGGER.debug(update_text)
        self.async_write_ha_state()
        async_call_later(self.hass, 3600, self.update_data)
