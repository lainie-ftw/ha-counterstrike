"""
The "hello world" custom component.

This component implements the bare minimum that a component should implement.

Configuration:

To use the hello_world component you will need to add the following to your
configuration.yaml file.

counterstrike:
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "counterstrike"


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up a skeleton component."""
    # States are in the format DOMAIN.OBJECT_ID.
    hass.states.set('counterstrike.Hello_World', 'Works!')

    # Return boolean to indicate that initialization was successfully.
    return True
"""
from datetime import datetime
from bs4 import BeautifulSoup
import urllib.request

#set up list of teams to get
team_list = ["Team_Liquid","G2_Esports", "Team_Falcons", "FaZe_Clan"]

#team = team_list[0]

for team in team_list:
  url = "https://liquipedia.net/counterstrike/" + team
  with urllib.request.urlopen(url) as response:
    # Read the content
    soup = BeautifulSoup(response, 'html.parser')

#get all the upcoming matches for the team
#tables = soup.find_all('table', class_="infobox_matches_content")

  #first table is the next event
  table = soup.find('table', class_="infobox_matches_content")

  #Timestamp of next match OR event is found in span class="timer-object"
  match_timestamp_span = table.find('span', class_="timer-object")
  if match_timestamp_span is not None:
    match_timestamp_string = match_timestamp_span['data-timestamp'].strip()
    match_timestamp = datetime.fromtimestamp(int(match_timestamp_string))
  else:
    match_timestamp = datetime.now()

  #rows[0] (tournament info) - if there's a td with class "team-right", that's a scheduled match and team-right is the opponent.
  # Otherwise it's a scheduled tournament appearance with no scheduled match yet.
  opponent = table.find('td', class_="team-right")
  if opponent is None:
    #tournament info is in a td with class="versus"
    tournament_name = table.find('td', class_="versus").text.strip()
    tournament_link = table.find('td', class_="versus").a['href'].strip()
    event = {
      "team": team,
      "type": "tournament",
      "opponent": None,
      "tournament":tournament_name,
      "link": "https://liquipedia.net" + tournament_link,
      "start_time": match_timestamp
    }
  else:
    #tournament info is in a div with class="tournament-text-flex"
    tournament_name = table.find('div', class_="tournament-text-flex").text.strip()
    tournament_link = table.find('div', class_="tournament-text-flex").a['href'].strip()
    opponent_name = opponent.find('span', class_="team-template-text").text.strip()
    event = {
      "team": team,
      "type": "match",
      "opponent": opponent_name,
      "tournament": tournament_name,
      "link": "https://liquipedia.net" + tournament_link,
      "start_time": match_timestamp
    }

  print(event)
"""
