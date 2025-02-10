import asyncio
from datetime import datetime, timedelta
import logging

import aiohttp
from bs4 import BeautifulSoup

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "counterstrike"
CONF_COUNTERSTRIKE = "counterstrike"

# update every hour
SCAN_INTERVAL = timedelta(seconds=3600)

# Data in attributes:
# team: abbrev, name, link, logo
# opponent: abbrev, name, link, logo
# tournament: name, link
# match: start time, view link

# Elements of the integration
CONF_TEAM = "team"
CONF_OPPONENT = "opponent"
CONF_TOURNAMENT = "tournament"
CONF_NEXT_MATCH = "next_match"

LIQUIPEDIA = "https://liquipedia.net/counterstrike/Liquipedia:Matches"


async def get_soup_object() -> BeautifulSoup:
    async with aiohttp.ClientSession() as session, session.get(LIQUIPEDIA) as response:
        html = await response.text()
        return BeautifulSoup(html, "html.parser")


async def async_setup(hass: HomeAssistant, config: ConfigType):
    devices = []

    teams = config[DOMAIN]

    for team_to_process in teams:
        team = team_to_process[CONF_TEAM]
        devices.append(CounterstrikeEntity(team, hass))

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

    def __init__(self, input_team, hass):
        self._unique_id = slugify(input_team)
        self._name = input_team
        self._team = None
        self._opponent = None
        self._tournament = None
        self._next_match = None

        self._state = None
        self._extra_state_attributes = None
        self.hass = hass

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
        soup = await get_soup_object()

        href_to_search = "/counterstrike/" + self._name
        team_link = soup.find(href=href_to_search)

        if team_link is not None:
            span = team_link.parent
            span_parent = span.parent
            td = span_parent.parent  # this is either team-right or team-left
            tr = td.parent
            team_match = tr.parent

            # span class="timer-object timer-object-countdown-only" data-timestamp="1737123900"
            match_timestamp_string = (
                team_match.find("span", class_="timer-object")["data-timestamp"]
            ).strip()
            match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
            # if match_timestamp <= datetime.now() and match_timestamp >= datetime.now():
            # only add upcoming matches
            team_left_full = team_match.find("td", class_="team-left")
            team_left_name = team_left_full.find(
                "span", class_="team-template-text"
            ).text
            team_left_link = team_left_full.find("a")["href"]
            team_left_abbrev = team_left_link.split("/")[-1]
            team_left_icon_url = team_left_full.find("img")["src"]

            team_right_full = team_match.find("td", class_="team-right")
            team_right_name = team_right_full.find(
                "span", class_="team-template-text"
            ).text
            team_right_link = team_right_full.find("a")["href"]
            team_right_abbrev = team_right_link.split("/")[-1]
            team_right_icon_url = team_right_full.find("img")["src"]

            if team_left_abbrev == self._name:
                self._team = {
                    "abbrev": team_left_abbrev,
                    "name": team_left_name,
                    "link": "https://liquipedia.net" + href_to_search,
                    "logo": "https://liquipedia.net" + team_left_icon_url,
                }
                self._opponent = {
                    "abbrev": team_right_abbrev,
                    "name": team_right_name,
                    "link": "https://liquipedia.net" + team_right_link,
                    "logo": "https://liquipedia.net" + team_right_icon_url,
                }
            else:
                self._team = {
                    "abbrev": team_right_abbrev,
                    "name": team_right_name,
                    "link": "https://liquipedia.net" + href_to_search,
                    "logo": "https://liquipedia.net" + team_right_icon_url,
                }
                self._opponent = {
                    "abbrev": team_left_abbrev,
                    "name": team_left_name,
                    "link": "https://liquipedia.net" + team_left_link,
                    "logo": "https://liquipedia.net" + team_left_icon_url,
                }

            self._tournament = {
                "name": "tournament woo",
                # "link":something,
            }
            self._next_match = {
                "start_time": match_timestamp,
                # "view_link":something,
            }
            self._state = self._next_match["start_time"]
        else:
            self._team = None
            self._opponent = None
            self._tournament = None
            self._next_match = None
            self._state = None

        self._extra_state_attributes = {
            CONF_TEAM: self._team,
            CONF_OPPONENT: self._opponent,
            CONF_TOURNAMENT: self._tournament,
            CONF_NEXT_MATCH: self._next_match,
        }
        _LOGGER.debug("Updated data")
        self.async_write_ha_state()
        async_call_later(self.hass, 3600, self.update_data)
