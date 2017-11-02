"""
NotOracle.py - a reporting bot for the /dev/null/tribute
NetHack tournament.
Copyright (c) 2017, A. Thomson

Concept based on the "oracle\devnull" bot of
#devnull_nethack 1999(?)-2016
Code based on Beholder of #hardfought - A.Thomson, K.Simpson.

which grew around the skeleton of:
deathbot.py - a game-reporting IRC bot for AceHack
Copyright (c) 2011, Edoardo Spadolini
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1. Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from twisted.internet import reactor, protocol, ssl, task
from twisted.words.protocols import irc
from twisted.python import filepath
from twisted.application import internet, service
from datetime import datetime, timedelta
import time     # for the indulgence of this bot's general time obsession
import ast      # for conduct/achievement bitfields - not really used
import os       # for check path exists (dumplogs), and chmod, and environ
import stat     # for chmod mode bits
import urllib   # for dealing with NH4 variants' #&$#@ spaces in filenames.
import json     # for trophies file
import random


# twitter - minimalist twitter api: http://mike.verdone.ca/twitter/
# pip install twitter
# set TWIT to false to prevent tweeting
TWIT = True
try:
    from twitter import Twitter, OAuth
except:
    TWIT = False

YEAR="2017" # Just in case we use this thing again

TEST= False
#TEST = True  # uncomment for testing

# fn
HOST, PORT = "chat.us.freenode.net", 6697
# Channels to log events only, not hourly reports
# Will speak when spoken to on any of these
EVENTCHANNELS = ["#hardfought"]
# Channels to log everything to
SPAMCHANNELS = ["#devnull_nethack"]

# only spam active channels
ACT_THRESHOLD = 5

NICK = "NotTheOracle\\dnt"
if TEST:
    EVENTCHANNELS = []
    SPAMCHANNELS = ["#hfdev"]
    NICK = "NotTheOracle\\tst"
    TWIT = False
CHANNELS = EVENTCHANNELS + SPAMCHANNELS
NOTIFY_PROXY = "Beholder" # just use Beholder's !tell for &notify
LOGROOT="/var/www/hardfought.org/irclog.dn/"
TROPHIES="/home/mandevil/trophies.json"
if TEST: TROPHIES="trophies.json"
# some lookup tables for formatting messages
role = { "Arc": "Archeologist",
         "Bar": "Barbarian",
         "Cav": "Caveman",
         "Hea": "Healer",
         "Kni": "Knight",
         "Mon": "Monk",
         "Pri": "Priest",
         "Ran": "Ranger",
         "Rog": "Rogue",
         "Sam": "Samurai",
         "Tou": "Tourist",
         "Val": "Valkyrie",
         "Wiz": "Wizard"
       }

race = { "Dwa": "Dwarf",
         "Elf": "Elf",
         "Gno": "Gnome",
         "Hum": "Human",
         "Orc": "Orc"
       }

align = { "Cha": "Chaotic",
          "Law": "Lawful",
          "Neu": "Neutral"
        }

gender = { "Mal": "Male",
           "Fem": "Female"
         }

t_recognition = {
    # bells trophies first
    "fullmonty_wbo" : "Full Monty (with bells on!)",
    "grandslam_wbo" : "Grand Slam (with bells on!)",
    "doubletop_wbo" : "Double Top (with bells on!)",
    "hattrick_wbo"  : "Hat-Trick (with bells on!)",
    "birdie_wbo"    : "Birdie (with bells on!)",
    "doubletop"     : "Double Top",
    "platinum"      : "Platinum Star",
    "fullmonty"     : "Full Monty",
    "birdie"        : "Birdie",
    "grandslam"     : "Grand Slam",
    "plastic"       : "Plastic Star",
    "dilithium"     : "Dilithium Star",
    "copper"        : "Copper Star",
    "iron"          : "Iron Star",
    "lead"          : "Lead Star",
    "gold"          : "Gold Star",
    "steel"         : "Steel Star",
    "bronze"        : "Bronze Star",
    "brass"         : "Brass Star",
    "zinc"          : "Zinc Star",
    "silver"        : "Silver Star",
    "hattrick"      : "Hat Trick"
}
t_major = {
    "bestinshow"    : "Best In Show",
    "unique"        : "Most Unique Deaths",
    "minscore"      : "Lowest Scored Ascension",
    "maxscore"      : "Highest Scored Ascension (aka the Berry)",
    "best13"        : "Grand Prize (Best of 13)",
    "minrealtime"   : "Lowest RealTime ascension",
    "mostascs"      : "Most Ascensions",
    "extinct"       : "Basic Extinct",
    "firstasc"      : "First Ascension",
    "bestconduct"   : "Best Behaved Ascension",
    "killionaire"   : "\"Who Wants to be a Killionaire?\"",
    "mingametime"   : "Lowest Turn-count Ascension"
}
t_minor = {
    "Arc" : "Highest Scored Archeologist",
    "Bar" : "Highest Scored Barbarian",
    "Cav" : "Highest Scored Caveman",
    "Hea" : "Highest Scored Healer",
    "Kni" : "Highest Scored Knight",
    "Mon" : "Highest Scored Monk",
    "Pri" : "Highest Scored Priest",
    "Ran" : "Highest Scored Ranger",
    "Rog" : "Highest Scored Rogue",
    "Sam" : "Highest Scored Samurai",
    "Tou" : "Highest Scored Tourist",
    "Val" : "Highest Scored Valkyrie",
    "Wiz" : "Highest Scored Wizard"
}
t_challenge = {
    "pacman" : "Pac-Man",
    "zapm"   : "ZAPM",
    "waldo"  : "Waldo",
    "pool"   : "Pool",
    "digdug" : "Dig-Dug",
    "joust"  : "Joust",
    "grue"   : "Grue"
}

def fromtimestamp_int(s):
    return datetime.fromtimestamp(int(s))

def timedelta_int(s):
    return timedelta(seconds=int(s))

def isodate(s):
    return datetime.strptime(s, "%Y%m%d").date()

def fixdump(s):
    return s.replace("_",":")

xlogfile_parse = dict.fromkeys(
    ("points", "deathdnum", "deathlev", "maxlvl", "hp", "maxhp", "deaths",
     "uid", "turns", "xplevel", "exp","depth","dnum","score","amulet","realtime"), int)
xlogfile_parse.update(dict.fromkeys(
    ("conduct", "event", "carried", "flags", "achieve"), ast.literal_eval))
#xlogfile_parse["starttime"] = fromtimestamp_int
#xlogfile_parse["curtime"] = fromtimestamp_int
#xlogfile_parse["endtime"] = fromtimestamp_int
#xlogfile_parse["realtime"] = timedelta_int
#xlogfile_parse["deathdate"] = xlogfile_parse["birthdate"] = isodate
#xlogfile_parse["dumplog"] = fixdump

def parse_xlogfile_line(line, delim):
    record = {}
    for field in line.strip().split(delim):
        key, _, value = field.partition("=")
        if key in xlogfile_parse:
            value = xlogfile_parse[key](value)
        record[key] = value
    return record

def parse_challenge_line(line,delim):
    record = dict(zip(["time","challenge","player","action"],line.strip().split(":")))
    return record

class DeathBotProtocol(irc.IRCClient):
    nickname = NICK
    username = "NotTheOracle"
    realname = "/dev/null/tribute"
    lineRate = 0.2
    admin = ["K2", "Tangles" ]  # for &notify
    try:
        password = open("/opt/NotOracle/pw", "r").read().strip() # We're not registering this with nickserv anyway
    except:
        pass
    if TEST: password = "NotTHEPassword"
    if TWIT:
       try:
           gibberish_that_makes_twitter_work = open("/opt/NotOracle/.twitter_oauth","r").read().strip().split("\n")
           twit = Twitter(auth=OAuth(*gibberish_that_makes_twitter_work))
       except:
           TWIT = False

    versionName = "NotOracle.py"
    versionNum = "0.1"

    dump_url_prefix = "https://"

    scoresURL = "https://www.hardfought.org/devnull"
    # devnull tournament runs on hollywood time
    os.environ["TZ"] = ":US/Pacific"
    ttime = { "start": datetime(int(YEAR),11,01,00,00,00),
              "end"  : datetime(int(YEAR),12,01,00,00,00)
            }
    servers = [ ("hardfought", "ssh nethack@hardfought.org   ", "US East"),
                ("altorg    ", "ssh nethack@e6.alt.org       ", "NAO Sponsored - US West"),
                ("hdf-eu    ", "ssh nethack@eu.hardfought.org", "EU (London)"),
                ("hdf-au    ", "ssh nethack@au.hardfought.org", "AU (Sydney)"),
              ]

    logday = time.strftime("%d")
    chanLog = {}
    chanLogName = {}
    activity = {}
    for c in CHANNELS:
        activity[c] = 0
        chanLogName[c] = LOGROOT + c + time.strftime("-%Y-%m-%d.log")
        try:
            chanLog[c] = open(chanLogName[c],'a')
        except:
            chanLog[c] = None
        if chanLog[c]: os.chmod(chanLogName[c],stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)

    # something else will have to retrieve the xlogfiles and place them locally
    xlogfiles = {filepath.FilePath("/var/www/hardfought.org/devnull/xlogfiles/xlogfile"): ("hardfought", "\t",
                                            "www.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath("/var/www/hardfought.org/devnull/xlogfiles/xlogfile-us-west"): ("altorg", "\t",
                                            "e6.alt.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath("/var/www/hardfought.org/devnull/xlogfiles/xlogfile-eu"): ("hdf-eu", "\t",
                                            "eu.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath("/var/www/hardfought.org/devnull/xlogfiles/xlogfile-au"): ("hdf-au", "\t",
                                            "au.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt")}
    # livelogs is actually just the challenge log at this point.
    livelogs  = {filepath.FilePath("/var/www/hardfought.org/challenge/dn36_log"): ("", ":")}
    # ZAPM logfiles 
    zlogfiles = [filepath.FilePath("/var/www/hardfought.org/challenge/zlogfile"),
                 filepath.FilePath("/var/www/hardfought.org/challenge/zlogfile-eu"),
                 filepath.FilePath("/var/www/hardfought.org/challenge/zlogfile-us-west")
                ]

    if TEST:
        xlogfiles = {filepath.FilePath("xlogfile.hdf"): ("hardfought", "\t",
                                            "www.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath("xlogfile.nao"): ("altorg", "\t",
                                            "e6.alt.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath("xlogfile.eu"): ("hdf-eu", "\t",
                                            "eu.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt")}
        # livelogs is actually just the challenge log at this point.
        livelogs  = {filepath.FilePath("dn36_log"): ("", ":")}


    looping_calls = None
    commands = {}

    def initStats(self, statset):
        self.stats[statset] = { "race"    : {},
                                "role"    : {},
                                "gender"  : {},
                                "align"   : {},
                                "points"  : 0,
                                "turns"   : 0,
                                "realtime": 0,
                                "games"   : 0,
                                "scum"    : 0,
                                "ascend"  : 0,
                                "zgames"  : 0,
                                "zascend" : 0
                              }
    def signedOn(self):
        self.factory.resetDelay()
        self.startHeartbeat()
        for c in CHANNELS:
            self.join(c)

        self.logs = {}
        for xlogfile, (variant, delim, dumpfmt) in self.xlogfiles.iteritems():
            self.logs[xlogfile] = (self.xlogfileReport, variant, delim, dumpfmt,parse_xlogfile_line)
        for livelog, (variant, delim) in self.livelogs.iteritems():
            self.logs[livelog] = (self.livelogReport, "", delim, "",parse_challenge_line)

        self.logs_seek = {}
        self.looping_calls = {}
        self.file_retries = 0

        #stats for hourly/daily spam
        self.stats = {}
        self.initStats("hour")
        self.initStats("day")
        # trophies...
        self.trophies = {}
        # work out how much hour is left
        nowtime = datetime.now()
        # add 1 hour, then subtract min, sec, usec to get exact time of next hour.
        nexthour = nowtime + timedelta(hours=1)
        nexthour -= timedelta(minutes=nexthour.minute,
                                       seconds=nexthour.second,
                                       microseconds=nexthour.microsecond)
        hourleft = (nexthour - nowtime).total_seconds() + 0.5 # start at 0.5 seconds past the hour.
        reactor.callLater(hourleft, self.startHourly)

        #lastgame shite
        self.lastgame = "No last game recorded"
        self.lg = {}
        self.lastasc = "No last ascension recorded"
        self.la = {}
        # for populating lg/la per player at boot, we need to track game end times
        # variant and variant:player don't need this if we assume the xlogfiles are
        # ordered within variant.
        self.lge = {}
        self.tlastgame = 0
        self.lae = {}
        self.tlastasc = 0

        self.commands = { "ping"     : self.doPing,
                          "time"     : self.doTime,
                          "notify"   : self.takeMessage,
                          "news"     : self.doNews,
                          "lastgame" : self.lastGame,
                          "lastasc"  : self.lastAsc,
                          "scores"   : self.doScoreboard,
                          "sb"       : self.doScoreboard,
                          "servers"  : self.doServers,
                          "help"     : self.doHelp
                        }

        # seek to end of livelogs
        for filepath in self.livelogs:
            with filepath.open("r") as handle:
                handle.seek(0, 2)
                self.logs_seek[filepath] = handle.tell()

        # likewise zapm logs
        for filepath in self.zlogfiles:
            with filepath.open("r") as handle:
                handle.seek(0, 2)
                self.logs_seek[filepath] = handle.tell()

        # sequentially read xlogfiles from beginning to pre-populate lastgame data.
        for filepath in self.xlogfiles:
            with filepath.open("r") as handle:
                for line in handle:
                    delim = self.logs[filepath][2]
                    game = self.logs[filepath][4](line, delim)
                    game["server"] = self.logs[filepath][1]
                    game["dumpfmt"] = self.logs[filepath][3]
                    for subline in self.logs[filepath][0](game,False):
                        pass
                self.logs_seek[filepath] = handle.tell()

        # poll logs for updates every 3 seconds
        for filepath in self.logs:
            self.looping_calls[filepath] = task.LoopingCall(self.logReport, filepath)
            self.looping_calls[filepath].start(3)

        # Additionally, keep an eye on our nick to make sure it's right.
        # Perhaps we only need to set this up if the nick was originally
        # in use when we signed on, but a 30-second looping call won't kill us
        self.looping_calls["nick"] = task.LoopingCall(self.nickCheck)
        self.looping_calls["nick"].start(30)
        # 1 minute looping call for trophies.
        self.looping_calls["trophy"] = task.LoopingCall(self.reportTrophies)
        self.looping_calls["trophy"].start(60)
        # Call it now to seed the trophy dict.
        self.reportTrophies()
        # Looping call for reporting zapm
        self.looping_calls["zapm"] = task.LoopingCall(self.reportZapm)
        self.looping_calls["zapm"].start(30)


    def tweet(self, message):
        if TWIT:
            try:
                self.twit.statuses.update(status=message)
            except:
                print "Bad tweet: " + message

    def nickCheck(self):
        # also rejoin the channel here, in case we drop off for any reason
        for c in CHANNELS: self.join(c)
        if (self.nickname != NICK):
            self.setNick(NICK)

    def nickChanged(self, nn):
        # catch successful changing of nick from above and identify with nickserv
        if TEST: self.msg("Tangles", "identify " + nn + " " + self.password)
        else: self.msg("NickServ", "identify " + nn + " " + self.password)

    def logRotate(self):
        self.logday = time.strftime("%d")
        for c in CHANNELS:
            if self.chanLog[c]: self.chanLog[c].close()
            self.chanLogName[c] = LOGROOT + c + time.strftime("-%Y-%m-%d.log")
            try: self.chanLog[c] = open(self.chanLogName[c],'a') # 'w' is probably fine here
            except: self.chanLog[c] = None
            if self.chanLog[c]: os.chmod(self.chanLogName[c],stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)

    # Write log
    def log(self, channel, message):
        if not self.chanLog[channel]: return
        # strip the colour control stuff out
        # This can probably all be done with a single RE but I have a headache.
        # message = re.sub(r'\x03\d\d,\d\d', '', message) # fg,bg pair
        # message = re.sub(r'\x03\d\d', '', message) # fg only
        # message = re.sub(r'[\x03\x0f]', '', message) # end of colour
        if time.strftime("%d") != self.logday: self.logRotate()
        self.chanLog[channel].write(time.strftime("%H:%M ") + message + "\n")
        self.chanLog[channel].flush()

    # wrapper for "msg" that logs if msg dest is channel
    # Need to log our own actions separately as they don't trigger events
    def msgLog(self, replyto, message):
        if replyto in CHANNELS:
            self.log(replyto, "<" + self.nickname + "> " + message)
        self.msg(replyto, message)

    def announce(self, message, spam = False):
        chanlist = CHANNELS
        if spam:
            chanlist = SPAMCHANNELS #only
        else: # only tweet non spam
            self.tweet(message)
        for c in chanlist:
            self.msgLog(c, message)

    # Similar wrapper for describe
    def describeLog(self, replyto, message):
        if replyto in CHANNELS:
            self.log(replyto, "* " + self.nickname + " " + message)
        self.describe(replyto, message)

    # construct and send response.
    # replyto is channel, or private nick
    # sender is original sender of query
    def respond(self, replyto, sender, message):
        if (replyto.lower() == sender.lower()): #private
            self.msg(replyto, message)
        else: #channel - prepend "Nick: " to message
#            self.msgLog(replyto, sender + ": " + message)
            self.msgLog(replyto, message)

    def reportZapm(self):
        for filepath in self.zlogfiles:
            with filepath.open("r") as handle:
                handle.seek(self.logs_seek[filepath])
                for line in handle:
                    print line
                    zwords = line.split()
                    self.announce("ZAPM: " + " ".join(zwords[5:]) + " [{0} points]".format(zwords[2]))
                    for period in self.stats:
                        if line.find("Activated the Bizarro Orgasmatron") != -1:
                            self.stats[period]["zascend"] += 1
                        self.stats[period]["zgames"] += 1
                self.logs_seek[filepath] = handle.tell()

    # Hourly/daily/special stats
    def spamStats(self,p,replyto):
        period = p
        if p == "news": period = "day"
        # formatting awkwardness
        # do turns and points, or time.
        stat1lst = [ "{turns} turns of NetHack were played and {points} points were scored.",
                      "{d} days, {h} hours, {m} minutes, and {s} seconds were spent playing NetHack."
                   ]
        zapmStr = [ "{zgames} games of ZAPM were played, with {zascend} ascensions." ]
        stat2str = { "align"  : "alignment" } # use get() to leave unchanged if not here
        periodStr = { "hour" : ["It's %H o'clock on %A, %B %d (%Z), and this is your Hourly Update.", "In the last hour,"],
                      "day"  : ["It's now %A, %B %d, and this is your Daily Wrap-up.", "Over the past day,"],
                      "news" : ["It's %M minutes after %H o'clock on %A, %B %d (%Z), and this is a Special Bulletin.", "So far today,"]
                    }
        # don't report zapm unless something was played
        if self.stats[period]["zgames"] > 0:
            stat1lst += zapmStr
        # hourly, we report one of role/race/etc. Daily, and for news, we report them all
        if p == "hour":
            stat1lst = [random.choice(stat1lst)]
            # weighted. role is more interesting than gender
            stat2lst = [random.choice(["role"] * 5 + ["race"] * 3 + ["align"] * 2 + ["gender"])]
        else:
            stat2lst = ["role", "race", "align", "gender"]
        if self.stats[period]["games"] != 0:
            # mash the realtime value into d,h,m,s
            rt = int(self.stats[period]["realtime"])
            self.stats[period]["s"] = int(rt%60)
            rt /= 60
            self.stats[period]["m"] = int(rt%60)
            rt /= 60
            self.stats[period]["h"] = int(rt%24)
            rt /= 24
            self.stats[period]["d"] = int(rt)

        cd = self.countDown()
        if cd["event"] == "start": cd["prep"] = "until"
        else: cd["prep"] = "in"
        if replyto:
            chanlist = [replyto]
        else:
            chanlist = SPAMCHANNELS
        for c in chanlist:
            self.msgLog(c, "Greetings, Adventurers!")
            self.msgLog(c, time.strftime(periodStr[p][0]))
            # for hourly, if it's slow report "hourly update" above, but give "so far today" stats below
            if p == "hour" and (self.stats[p]["games"] - self.stats[p]["scum"] < 10):
                p = "news"
                period = "day"
            self.msgLog(c, periodStr[p][1] + " {games} games of NetHack ended, with {ascend} ascensions, and {scum} start-scums.".format(**self.stats[period]))
            if self.stats[period]["games"] != 0:
                for stat1 in stat1lst:
                    self.msgLog(c, stat1.format(**self.stats[period]))
                for stat2 in stat2lst:
                    # Find whatever thing from the list above had the most games, and how many games it had
                    maxStat2 = dict(zip(["name","number"],max(self.stats[period][stat2].iteritems(), key=lambda x:x[1])))
                    # Expand the Rog->Rogue, Fem->Female, etc
                    maxStat2["name"] = dict(role.items() + race.items() + gender.items() + align.items()).get(maxStat2["name"],maxStat2["name"])
                    self.msgLog(c, "The most popular NetHack " + stat2str.get(stat2,stat2) + " was {name} with {number} games.".format(**maxStat2))
            self.msgLog(c, "There are {days} days, {hours} hours and {minutes} minutes left {prep} the ".format(**cd)
                               + YEAR + " Tournament")
            self.msgLog(c, "Let's be careful out there.")

    def startCountdown(self,event,time):
        self.announce("The tournament {0}s in {1}...".format(event,time),True)
        for delay in range (1,time):
            reactor.callLater(delay,self.announce,"{0}...".format(time-delay),True)

#    def testCountdown(self, sender, replyto, msgwords):
#        self.startCountdown(msgwords[1],int(msgwords[2]))

    def hourlyStats(self):
        nowtime = datetime.now()
        # special case handling for start/end
        # we are running at the top of the hour
        # so checking we are within 1 minute of start/end time is sufficient
        if abs(nowtime - self.ttime["start"]) < timedelta(minutes=1):
            self.announce("###### THE {0} DEVNULL TRIBUTE TOURNAMENT IS OPEN! ######".format(YEAR))
        elif abs(nowtime - self.ttime["end"]) < timedelta(minutes=1):
            self.announce("###### THE {0} DEVNULL TRIBUTE TOURNAMENT IS CLOSED! ######".format(YEAR))
        elif abs(nowtime + timedelta(hours=1) - self.ttime["start"]) < timedelta(minutes=1):
            reactor.callLater(3597, self.startCountdown,"start",3) # 3 seconds to the next hour
        elif abs(nowtime + timedelta(hours=1) - self.ttime["end"]) < timedelta(minutes=1):
            reactor.callLater(3597, self.startCountdown,"end",3) # 3 seconds to the next hour
        game_on =  (nowtime > self.ttime["start"]) and (nowtime < self.ttime["end"])
        #if TEST: game_on = True
        if not game_on: return

        if nowtime.hour == 0:
            self.spamStats("day",None)
            self.initStats("day")
        else:
            self.spamStats("hour",None)
        self.initStats("hour")

    def startHourly(self):
        # this is scheduled to run at the first :00 after the bot starts
        # makes a looping_call to run every hour from here on.
        self.looping_calls["stats"] = task.LoopingCall(self.hourlyStats)
        self.looping_calls["stats"].start(3600)

    # Countdown timer
    def countDown(self):
        cd = {}
        for event in ("start", "end"):
            cd["event"] = event
            # add half a second for rounding (we truncate at the decimal later)
            td = (self.ttime[event] - datetime.now()) + timedelta(seconds=0.5)
            sec = int(td.seconds)
            cd["seconds"] = int(sec % 60)
            cd["minutes"] = int((sec / 60) % 60)
            cd["hours"] = int(sec / 3600)
            cd["days"] = td.days
            cd["countdown"] = td
            if td > timedelta(0):
                return cd
        return cd

    def listTrophies(self,tlist):
        # take a list of trophy IDs and expand them to full names
        # return a string of the list like "this, that, and the other thing"
        rv = ''
        for i,t in enumerate(tlist):
            # this is a nasty way to find the trophy name in any category
            tname = t_major.get(t,t_minor.get(t,t_recognition.get(t,t)))
            # first item
            if (i == 0):
               rv = tname
            # last item
            elif (i == len(tlist)-1):
               if (i > 1): rv += "," # oxford comma :P
               rv += " and " + tname
            # middle items
            else:
               rv += ", " + tname
        return rv

    def reportTrophies(self):
        #try:
        ntrophies = json.loads(open(TROPHIES).read())
        #except:
        #    print "Failed to read trophies file: " + TROPHIES
        #    return
        if self.trophies == {}:
            # bot probably restarted
            self.trophies = ntrophies
            return
        newplrtrophies = {}
        firstasc = ''
        for tr in t_major.keys():
            if self.trophies[tr] != ntrophies[tr]:
                # first ascension gets special treatment
                if tr == "firstasc":
                    firstasc = ntrophies[tr].encode("utf-8")
                    print "first asc: " + firstasc
                else:
                    newplrtrophies[ntrophies[tr]] = newplrtrophies.get(ntrophies[tr],[]) + [tr]

        for tr in t_minor.keys():
            if self.trophies["minor"][tr] != ntrophies["minor"][tr]:
                newplrtrophies[ntrophies["minor"][tr]] = newplrtrophies.get(ntrophies["minor"][tr],[]) + [tr]

        newrec = {}
        for tr in t_recognition.keys():
            for nm in ntrophies[tr]:
                if not nm in self.trophies[tr]:
                    newrec[nm] = newrec.get(nm,[]) + [tr]
        self.trophies = ntrophies

        if firstasc:
            self.announce("TROPHY: " + firstasc + " just bagged the first ascension!")
        for plr in newplrtrophies.keys():
            self.announce("TROPHY: " + plr.encode("utf-8") + " now holds the " + self.listTrophies(newplrtrophies[plr]))
        for plr in newrec.keys():
            self.announce("TROPHY: " + plr.encode("utf-8") + " just earned the " + self.listTrophies(newrec[plr]))

    # implement commands here
    def doPing(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "Pong! " + " ".join(msgwords[1:]))

    def doTime(self, sender, replyto, msgwords):

        self.respond(replyto, sender, time.strftime("The time is %H:%M:%S(%Z) on %A, %B %d, %Y"))
        timeLeft = self.countDown()
        if timeLeft["countdown"] <= timedelta(0):
            self.msgLog(c, "The " + YEAR + " tournament is OVER!")
            return
        verbs = { "start" : "begins",
                  "end" : "closes"
                }

        self.respond(replyto, sender, "The time remaining until the " + YEAR + " Tournament "
                                      + verbs[timeLeft["event"]]
                                      + " is '00-00-{days:0>2}:{hours:0>2}-{minutes:0>2}-{seconds:0>2}'".format(**timeLeft))


    def doNews(self, sender, replyto, msgwords):
        self.spamStats("news",replyto)

    def doScoreboard(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "Please see " + self.scoresURL + " for the current standings.")

    def doServers(self, sender, replyto, msgwords):
        for s in self.servers:
            self.respond(replyto,sender, " : ".join(s))

    def doHelp(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "&ping    - ping!\n"
                                    + "&time    - Get time remaining\n"
                                    + "&news    - request a tournament news bulletin\n"
                                    + "&notify  - Send message to tournament staff\n"
                                    + "&lastgame/&lastasc - dumplogs from last game for player/server\n"
                                    + "&scores  - Link to scoreboard\n"
                                    + "&servers - List of servers where you can play\n"
                                    + "&help    - This help.")

    def takeMessage(self, sender, replyto, msgwords):
        for a in self.admin:
            # make some other bot deal with the message
            self.msg(NOTIFY_PROXY, "!tell " + a + " " + sender + " said " + " ".join(msgwords[1:]))
        self.msgLog(replyto,"Message sent to tournament admins on behalf of " + sender + ".")

    def lastGame(self, sender, replyto, msgwords):
        if (len(msgwords) >= 3): #var, plr, any order.
#            vp = self.varalias(msgwords[1])
#            pv = self.varalias(msgwords[2])
            vp = msgwords[1].lower()
            pv = msgwords[2].lower()
            #dl = self.lg.get(":".join(msgwords[1:3]).lower(), False)
            dl = self.lg.get(":".join([vp,pv]).lower(), False)
            if not dl:
                #dl = self.lg.get(":".join(msgwords[2:0:-1]).lower(),
                dl = self.lg.get(":".join([pv,vp]).lower(),
                                 "No last game for (" + ",".join(msgwords[1:3]) + ")")
            self.respond(replyto, sender, dl)
            return
        if (len(msgwords) == 2): #var OR plr - don't care which
            #vp = self.varalias(msgwords[1])
            vp = msgwords[1].lower()
            dl = self.lg.get(vp,"No last game for " + msgwords[1])
            self.respond(replyto, sender, dl)
            return
        self.respond(replyto, sender, self.lastgame)

    def lastAsc(self, sender, replyto, msgwords):
        if (len(msgwords) >= 3): #var, plr, any order.
            #vp = self.varalias(msgwords[1])
            #pv = self.varalias(msgwords[2])
            vp = msgwords[1].lower()
            pv = msgwords[2].lower()
            dl = self.la.get(":".join(pv,vp).lower(),False)
            if (dl == False):
                dl = self.la.get(":".join(vp,pv).lower(),
                                 "No last ascension for (" + ",".join(msgwords[1:3]) + ")")
            self.respond(replyto, sender, dl)
            return
        if (len(msgwords) == 2): #var OR plr - don't care which
            #vp = self.varalias(msgwords[1])
            vp = msgwords[1].lower()
            dl = self.la.get(vp,"No last ascension for " + msgwords[1])
            self.respond(replyto, sender, dl)
            return
        self.respond(replyto, sender, self.lastasc)

    # Listen to the chatter
    def privmsg(self, sender, dest, message):
        sender = sender.partition("!")[0]
        if (dest in CHANNELS): #public message
            self.log(dest, "<"+sender+"> " + message)
            replyto = dest
            self.activity[dest] += 1
        else: #private msg
            replyto = sender
        # ignore other channel noise unless &command
        if (message[0] != '&'):
            if (dest in CHANNELS): return
        else: # pop the '&'
            message = message[1:]
        msgwords = message.strip().split(" ")
        if self.commands.get(msgwords[0].lower(), False):
            self.commands[msgwords[0].lower()](sender, replyto, msgwords)

    #other events for logging
    def action(self, doer, dest, message):
        if (dest in CHANNELS):
            doer = doer.split('!', 1)[0]
            self.log(dest, "* " + doer + " " + message)
            self.activity[dest] += 1

    def userRenamed(self, oldName, newName):
        for c in CHANNELS: self.log(c, "-!- " + oldName + " is now known as " + newName)

    def noticed(self, user, channel, message):
        if (channel in CHANNELS):
            user = user.split('!')[0]
            self.log(channel, "-" + user + ":" + channel + "- " + message)

    def modeChanged(self, user, channel, set, modes, args):
        if (set): s = "+"
        else: s = "-"
        user = user.split('!')[0]
        if channel in CHANNELS:
            if args[0]:
                self.log(channel, "-!- mode/" + channel + " [" + s + modes + " " + " ".join(list(args)) + "] by " + user)
            else:
                self.log(channel, "-!- mode/" + channel + " [" + s + modes + "] by " + user)

    def userJoined(self, user, channel):
        #(user,details) = user.split('!')
        #self.log("-!- " + user + " [" + details + "] has joined " + channel)
        self.log(channel, "-!- " + user + " has joined " + channel)
        # joins count as activity, leaves/quits don't
        self.activity[channel] += 1

    def userLeft(self, user, channel):
        #(user,details) = user.split('!')
        #self.log("-!- " + user + " [" + details + "] has left " + channel)
        self.log(channel, "-!- " + user + " has left " + channel)

    def userQuit(self, user, quitMsg):
        #(user,details) = user.split('!')
        #self.log("-!- " + user + " [" + details + "] has quit [" + quitMsg + "]")
        for c in CHANNELS: self.log(c, "-!- " + user + " has quit [" + quitMsg + "]")

    def userKicked(self, kickee, channel, kicker, message):
        kicker = kicker.split('!')[0]
        kickee = kickee.split('!')[0]
        self.log(channel, "-!- " + kickee + " was kicked from " + channel + " by " + kicker + " [" + message + "]")

    def topicUpdated(self, user, channel, newTopic):
        user = user.split('!')[0]
        self.log(channel, "-!- " + user + " changed the topic on " + channel + " to: " + newTopic)
        self.activity[channel] += 1


    ### Xlog/challenge event processing
    def startscummed(self, game):
        return game["death"] in ("quit", "escaped") and game["points"] < 1000

    def xlogfileReport(self, game, report = True):

        scumbag = self.startscummed(game)

        # collect hourly/daily stats for games that actually ended within the period
        etime = fromtimestamp_int(game["endtime"])
        ntime = datetime.now()
        et = {}
        nt = {}
        et["hour"] = datetime(etime.year,etime.month,etime.day,etime.hour)
        et["day"] = datetime(etime.year,etime.month,etime.day)
        nt["hour"] = datetime(ntime.year,ntime.month,ntime.day,ntime.hour)
        nt["day"] = datetime(ntime.year,ntime.month,ntime.day)
        for period in ["hour","day"]:
            if et[period] == nt[period]:
                self.stats[period]["games"] += 1
                if scumbag: self.stats[period]["scum"] += 1
                for tp in ["turns","points","realtime"]:
                    self.stats[period][tp] += game[tp]
                for rrga in ["role","race","gender","align"]:
                    self.stats[period][rrga][game[rrga]] = self.stats[period][rrga].get(game[rrga],0) + 1
                if game["death"] == "ascended":
                    self.stats[period]["ascend"] += 1

        if scumbag: return

        lname = game["name"].lower()
        var = game["server"].lower() # var is server, formerly variant.

        dumplog = game.get("dumplog",False)
        # Need to figure out the dump path before messing with the name below
        # quote only the game-specific part, not the prefix.
        # Otherwise it quotes the : in https://
        # assume the rest of the url prefix is safe.
        dumpurl = urllib.quote(game["dumpfmt"].format(**game))
        dumpurl = self.dump_url_prefix.format(**game) + dumpurl
        self.lg[lname] = dumpurl
        if (game["endtime"] > self.lge.get(lname, 0)):
            self.lge[lname] = game["endtime"]
            self.lg[lname] = dumpurl
        self.lg[var] = dumpurl
        if (game["endtime"] > self.tlastgame):
            self.lastgame = dumpurl
            self.tlastgame = game["endtime"]

        if game["death"][0:8] in ("ascended"):
            # append dump url to report for ascensions
            game["ascsuff"] = "\n" + dumpurl
            # !lastasc stats.
            self.la["{server}:{name}".format(**game).lower()] = dumpurl
            if (game["endtime"] > self.lae.get(lname, 0)):
                self.lae[lname] = game["endtime"]
                self.la[lname] = dumpurl
            self.la[var] = dumpurl
            if (game["endtime"] > self.tlastasc):
                self.lastasc = dumpurl
                self.tlastasc = game["endtime"]
        else:
            game["ascsuff"] = ""

        if (not report): return # we're just reading through old entries at startup
        # start of actual reporting
        if game.get("while", False) and game["while"] != "":
            game["death"] += (", while " + game["while"])

        # Make reports look like the old oracle\devnull messages
        # Format taken from the old twitter feed which has not worked since 2012
        # as I have no irc logs, but I think it's the same.
        if game["death"] in ("quit", "escaped", "ascended"):
            END = game["death"].upper()
        else: END = "DIED"
        yield (END + ": {name} ({role}-{race}-{gender}-{align}), "
                   "{points} points, {turns} turns, {death} on {server}{ascsuff}").format(**game)

    # actually "challenge" log reporting
    def livelogReport(self, event):
       actioned = { "accept": "accepted", "success": "completed", "ignore": "ignored" }
       event["acted"] = actioned[event["action"]]
       event["chalname"] = t_challenge[event["challenge"].lower()]
       yield ("CHALLENGE " + event["acted"].upper() + "! {player} {acted} the {chalname} challenge.".format(**event))

    def logReport(self, filepath):
        with filepath.open("r") as handle:
            handle.seek(self.logs_seek[filepath])

            for line in handle:
                delim = self.logs[filepath][2]
                game = self.logs[filepath][4](line, delim)
                if self.logs[filepath][1]: game["server"] = self.logs[filepath][1]
                if self.logs[filepath][3]: game["dumpfmt"] = self.logs[filepath][3]
                #try:
                for subline in self.logs[filepath][0](game):
                    self.announce(subline)
                #except:
                #    print "LogReport: Bad line: " + line
                #    self.file_retries += 1
                #    if self.file_retries < 5:
                #        return # without updating logs_seek.
                        # we will try again from beginning of this line
                #    else:
                        # retries exceeded - give up and resume from EOF.
                #        self.file_retries = 0
                #        handle.seek(0,2)
            self.logs_seek[filepath] = handle.tell()


    def connectionLost(self, reason=None):
        if self.looping_calls is None: return
        for call in self.looping_calls.itervalues():
            call.stop()


if __name__ == "__builtin__":
    f = protocol.ReconnectingClientFactory()
    f.protocol = DeathBotProtocol
    application = service.Application("DeathBot")
    deathservice = internet.SSLClient(HOST, PORT, f,
                                      ssl.ClientContextFactory())
    deathservice.setServiceParent(application)
