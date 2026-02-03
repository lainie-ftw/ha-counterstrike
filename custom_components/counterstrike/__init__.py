import asyncio
from datetime import datetime, timedelta
import logging

import aiohttp
from dateutil import parser as date_parser

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

PANDASCORE_API_KEY = ""

# Data in attributes:
# team: abbrev, name, link, logo
# opponent: abbrev, name, link, logo
# tournament: name, link
# match: start time, view link

async def async_setup(hass: HomeAssistant, config: ConfigType):
    devices = []

    teams = config[DOMAIN]

    for team_to_process in teams:
        team = team_to_process["team"]
        show_score = team_to_process["show_score"]
        devices.append(CounterstrikeEntity(team, show_score, hass))

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

    def __init__(self, input_team, show_score,hass):
        team_id = input_team
        self._unique_id = slugify(team_id)
        self._name = team_id
        self._team_name = input_team
        self._team = None
        self._opponent = None
        self._tournament = None
        self._next_match = None

        self._state = "NOT_FOUND"
        self._extra_state_attributes = None

        self._show_score = show_score
        self.hass = hass

    async def fetch_team_match(self) -> dict:
        """
        Fetch the most recent match for a team using the PandaScore API.
        
        Args:
            team_slug: Team slug (e.g., "falcons-esports", "mousesports-cs-go")
            
        Returns:
            dict: Match data or None if not found
        """
        # Construct API URL
        api_url = f"https://api.pandascore.co/teams/{self.name}/matches"
        params = {
            "videogame_title": "cs-2",
            "page[size]": "1"
        }
        
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {PANDASCORE_API_KEY}"
        }
        
        try:
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, headers=headers) as response:
                    if response.status != 200:
                        # handle error
                        return None
                    matches = await response.json()
            
            if not matches or len(matches) == 0:
                _LOGGER.info("no matches found")
                return None
            
            # Get the first match (most recent)
            match_data = matches[0]
            
            # Extract match timestamp
            scheduled_at = match_data.get("scheduled_at") or match_data.get("begin_at")
            if not scheduled_at:
                return None
            
            _LOGGER.info("made it past the API call and the scheduled_at time")

            # Parse ISO 8601 timestamp to datetime
            match_timestamp = date_parser.isoparse(scheduled_at)
            match_timestamp_string = str(int(match_timestamp.timestamp()))
            
            # Determine match status
            api_status = match_data.get("status", "not_started")
            status_map = {
                "not_started": "PRE",
                "running": "PRE",
                "finished": "POST"
            }
            match_status = status_map.get(api_status, "PRE")
            
            # Extract opponents
            opponents = match_data.get("opponents", [])
            
            # Handle case where opponents array is empty or has less than 2 teams
            if len(opponents) < 2:
                # Try to get at least our team
                if len(opponents) == 1:
                    team_data = opponents[0].get("opponent", {})
                    
                    team = {
                        "abbrev": team_data.get("slug", team_data.get("acronym", self.name)),
                        "name": team_data.get("name", "Unknown"),
                        "link": f"https://liquipedia.net/counterstrike/{self.name}",
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
                        "abbrev": self.name,
                        "name": self.name.replace("-", " ").replace("_", " ").title(),
                        "link": f"https://liquipedia.net/counterstrike/{self.name}",
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
            else:
                # Determine which opponent is our team
                team_data = None
                opponent_data = None
                
                for opp in opponents:
                    opp_info = opp.get("opponent", {})
                    opp_slug = opp_info.get("slug", "")
                    
                    # Try to match by slug (handle both dash and underscore variations)
                    normalized_team_slug = self.name.replace("_", "-")
                    normalized_opp_slug = opp_slug.replace("_", "-")
                    
                    if normalized_opp_slug == normalized_team_slug:
                        team_data = opp_info
                    else:
                        opponent_data = opp_info
                
                # If we couldn't match by slug, just use the first two opponents
                if not team_data or not opponent_data:
                    team_data = opponents[0].get("opponent", {})
                    opponent_data = opponents[1].get("opponent", {})
                
                # Extract scores from results array if we want to see scores                
                team_score = None
                opponent_score = None
                if self.show_score:
                    results = match_data.get("results", [])
                    
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
                team_slug_clean = team_data.get("slug", team_data.get("acronym", self.name))
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
            
            return result
                
        except Exception as e:
            _LOGGER.info("caught an exception: %s", e)
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
        _LOGGER.info("In update_data for %s", self._team_name)
 
        result = await self.fetch_team_match()

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
        )
        _LOGGER.debug(update_text)
        self.async_write_ha_state()
        async_call_later(self.hass, 3600, self.update_data)
