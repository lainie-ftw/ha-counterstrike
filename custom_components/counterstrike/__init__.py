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

LIQUIPEDIA = "https://liquipedia.net/counterstrike/Liquipedia:Matches"


async def get_soup_object(link) -> BeautifulSoup:
    async with aiohttp.ClientSession() as session, session.get(link) as response:
        html = await response.text()
        return BeautifulSoup(html, "html.parser")


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

    _LOGGER.debug(devices)

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

        if upcoming_or_concluded == "upcoming":
            self._match_state = "1"
        else:
            self._match_state = "2"

        self._show_score = show_score
        self.hass = hass

    async def process_match(self, team_link):
        match_status = "NOT_FOUND"
        href_to_search = self._team_name

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
            _LOGGER.error("Could not find match container (new-match-style div)")
            return

        # Match timestamp
        timer_span = team_match.find("span", class_="timer-object")
        if timer_span is None:
            _LOGGER.error("Could not find timer-object span")
            return
            
        match_timestamp_string = timer_span.get("data-timestamp", "").strip()
        if not match_timestamp_string:
            _LOGGER.error("Could not find data-timestamp attribute")
            return
            
        match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))

        # Get match info header to access teams and score
        match_info_header = team_match.find("div", class_="match-info-header")
        if not match_info_header:
            _LOGGER.error("Could not find match-info-header")
            return

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

        # Extract scores if match is POST or IN and show_score is true
        team_left_score = None
        team_right_score = None
        if self._show_score and match_status in ("POST", "IN") and score_holder:
            score_upper = score_holder.find("span", class_="match-info-header-scoreholder-upper")
            if score_upper and ":" in score_upper.text:
                score_parts = score_upper.text.split(":")
                team_left_score = score_parts[0].strip()
                team_right_score = score_parts[1].strip()

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
        else:
            # Get live/upcoming stream links
            tournament_livestreams_yt = None
            if tournament_section:
                tournament_livestreams_yt = tournament_section.find(href=re.compile("youtube"))
            if streams_section and not tournament_livestreams_yt:
                tournament_livestreams_yt = streams_section.find(href=re.compile("youtube"))
                
            if tournament_livestreams_yt is not None:
                livestream_yt_link = "https://liquipedia.net" + tournament_livestreams_yt["href"]
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

        if team_left_abbrev == self._team_name:
            self._team = {
                "abbrev": team_left_abbrev,
                "name": team_left_name,
                "link": "https://liquipedia.net/counterstrike/" + href_to_search,
                "logo": "https://liquipedia.net" + team_left_icon_url,
                "score": team_left_score,
            }
            self._opponent = {
                "abbrev": team_right_abbrev,
                "name": team_right_name,
                "link": "https://liquipedia.net" + team_right_link,
                "logo": "https://liquipedia.net" + team_right_icon_url,
                "score": team_right_score,
            }
        else:
            self._team = {
                "abbrev": team_right_abbrev,
                "name": team_right_name,
                "link": "https://liquipedia.net/counterstrike/" + href_to_search,
                "logo": "https://liquipedia.net" + team_right_icon_url,
                "score": team_right_score,
            }
            self._opponent = {
                "abbrev": team_left_abbrev,
                "name": team_left_name,
                "link": "https://liquipedia.net" + team_left_link,
                "logo": "https://liquipedia.net" + team_left_icon_url,
                "score": team_left_score,
            }

        self._tournament = {
            "name": tournament_name,
            "link": "https://liquipedia.net" + tournament_link,
        }
        self._next_match = {
            "start_time": match_timestamp,
            "view_links": livestream_list,
        }

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
            "view_links": self._next_match["view_links"],
            "last_update": datetime.now(),
        }

        if (
            match_status == "IN"
        ):  # the IN status is super ugly with the info I have right now, so...make it look like "POST" instead
            match_status = "PRE"
        self._state = match_status

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
        soup = await get_soup_object(LIQUIPEDIA)

        href_to_search = "/counterstrike/" + self._team_name
        team_link_all = soup.find_all(href=href_to_search)

        if team_link_all is not None:
            find_matches = soup.find(
                "div", attrs={"data-toggle-area-content": self._match_state}
            )
            team_find_match = find_matches.find(href=href_to_search)
            if team_find_match is not None:
                await self.process_match(team_find_match)

        if team_link_all is None or team_find_match is None:
            self._state = "NOT_FOUND"
            self._extra_state_attributes = {
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