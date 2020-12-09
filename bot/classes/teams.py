# @CHECK 2.0 features OK

""" Basic team object, should be explicit
"""

from modules.enumerations import PlayerStatus
from classes.players import ActivePlayer # ok


class Team:
    def __init__(self, id, name, match):
        self.__id = id
        self.__name = name
        self.__players = list()
        self.__score = 0
        self.__net = 0
        self.__deaths = 0
        self.__kills = 0
        self.__faction = 0
        self.__cap = 0
        self.__match = match

    @classmethod
    def new_from_data(cls, i, data, match):
        obj = cls(i, data["name"], match)
        obj.__faction = data["faction_id"]
        obj.__score = data["score"]
        obj.__net = data["net"]
        obj.__deaths = data["deaths"]
        obj.__kills = data["kills"]
        obj.__cap = data["cap_points"]
        for p_data in data["players"]:
            obj.__players.append(ActivePlayer.new_from_data(p_data, obj))
        return obj

    def get_data(self):
        players_data = list()
        for p in self.__players:
            players_data.append(p.get_data())
        data = {"name": self.__name,
                "faction_id": self.__faction,
                "score": self.__score,
                "net": self.__net,
                "deaths": self.deaths,
                "kills": self.__kills,
                "cap_points": self.__cap,
                "players": players_data
                }
        return data

    @property
    def id(self):
        return self.__id

    @property
    def ig_string(self):
        p_string = ",".join(p.ig_name for p in self.__players)
        return f"{self.__name}: `{p_string}`"

    @property
    def name(self):
        return self.__name

    @property
    def players(self):
        return self.__players

    @property
    def faction(self):
        return self.__faction

    @faction.setter
    def faction(self, faction):
        self.__faction = faction

    @property
    def score(self):
        return self.__score

    @property
    def net(self):
        return self.__net

    @property
    def cap(self):
        return self.__cap
    
    @property
    def kills(self):
        return self.__kills
    
    @property
    def deaths(self):
        return self.__deaths

    @property
    def player_pings(self):
        # Excluding captain
        pings = [p.mention for p in self.__players[1:]]
        return pings

    @property
    def all_pings(self):
        # All players with captain
        pings = [p.mention for p in self.__players]
        return pings

    @property
    def captain(self):
        return self.__players[0]

    @property
    def is_players(self):
        return len(self.__players) > 1

    @property
    def match(self):
        return self.__match
    
    def clear(self):
        self.__players.clear()

    def add_cap(self, points):
        self.__cap += points
        self.__score += points
        # self.__net += points

    def add_score(self, points):
        self.__score += points

    def add_net(self, points):
        self.__net += points

    def add_one_kill(self):
        self.__kills += 1

    def add_one_death(self):
        self.__deaths += 1

    def add_player(self, cls, player):
        active = cls(player, self)
        self.__players.append(active)
    
    def on_team_ready(self):
        for aP in self.__players:
            aP.on_team_ready()

    def on_match_ready(self):
        for p in self.__players:
            p.on_match_ready()

    def on_player_sub(self, subbed, new_player):
        i = 0
        while self.__players[i] is not subbed:
            i+=1
        active = type(subbed)(new_player, self)
        self.__players[i] = active
