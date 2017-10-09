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
#import re       # for hello, and other things.
import urllib   # for dealing with NH4 variants' #&$#@ spaces in filenames.
#import shelve   # for perstistent !tell messages
#import random   # for !rng and friends
#import glob     # for matchning in !whereis

# set TWIT to false to prevent tweeting
TWIT = True
try:
    from twitter import Twitter, OAuth
except:
    TWIT = False

TEST= False
#TEST = True  # uncomment for testing

# fn
HOST, PORT = "chat.us.freenode.net", 6697
# Channels to log events only, not hourly reports
EVENTCHANNELS = ["#hardfought"]
# Channels to log everything to
# I kinda think we need to go there.
SPAMCHANNELS = ["#devnull_nethack"]

# only spam active channels
ACT_THRESHOLD = 5

NICK = "NotTheOracle\\dnt"
if TEST:
    EVENTCHANNELS = ["#bot-test"]
    SPAMCHANNELS = ["#hfdev"]
    NICK = "NotTheOracle"
CHANNELS = EVENTCHANNELS + SPAMCHANNELS
NOTIFY_PROXY = "Beholder" # just use Beholder's !tell for &notify
FILEROOT="/opt/nethack/hardfought.org/"
WEBROOT="https://www.hardfought.org/"
LOGROOT="/var/www/hardfought.org/irclog.dn/"

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
     "uid", "turns", "xplevel", "exp","depth","dnum","score","amulet"), int)
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

#def xlogfile_entries(fp):
#    if fp is None: return
#    with fp.open("rt") as handle:
#        for line in handle:
#            yield parse_xlogfile_line(line)

class DeathBotProtocol(irc.IRCClient):
    nickname = NICK
    username = "NotTheOracle"
    realname = "/dev/null/tribute"
    admin = ["K2", "Tangles" ]  # for &notify
    try:
        password = open("/opt/NotTheOracle/pw", "r").read().strip() # We're not registering this with nickserv anyway
    except:
        pass
    if TEST: password = "NotTHEPassword"
    if TWIT:
       try:
           gibberish_that_makes_twitter_work = open(".twitter_oauth","r").read().strip().split("\n")
           #gibberish_that_makes_twitter_work = open("/opt/NotTheOracle/.twitter_oauth","r").read().strip().split("\n")
           twit = Twitter(auth=OAuth(*gibberish_that_makes_twitter_work))
       except:
           TWIT = False
    
    
#    sourceURL = "https://github.com/NHTangles/beholder"
    versionName = "NotOracle.py"
    versionNum = "0.1"

    dump_url_prefix = "https://" # WEBROOT + "userdata/{name[0]}/{name}/"
    dump_file_prefix = FILEROOT + "dgldir/userdata/{name[0]}/{name}/"
    
    scoresURL = "https://www.hardfought.org/___coming_soon___"
    if TEST: scoresURL = "https://voyager.lupomesky.cz/dnt/test.html"
#    rceditURL = WEBROOT + "nethack/rcedit"
#    helpURL = WEBROOT + "nethack"
    # devnull tournament runs on hollywood time
    os.environ["TZ"] = ":US/Pacific"
    ttime = { "start": datetime(2017,11,01,00,00,00),
              "end"  : datetime(2017,12,01,00,00,00)
            }
    servers = [ ("hardfought", "ssh nethack@hardfought.org", "US East"),
                ("altorg    ", "ssh nethack@e6.alt.org    ", "NAO Sponsored - US West"),
                ("hdf-eu    ", "coming soon               ", "EU (London)"),
                ("hdf-au    ", "coming maybe :)           ", "AU (Sydney)"),
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

    # This will need some work.  Dumplog paths for remote servers.
    # something else will have to retrieve the xlogfiles and place them locally
    xlogfiles = {filepath.FilePath(FILEROOT+"devnull36/var/xlogfile"): ("hardfought", "\t",
                                            "www.hardfought.org/userdata/{name[0]}/{name}/dn36/dumplog/{starttime}.dn36.txt"),
                 filepath.FilePath(FILEROOT+"devnull36/var/xlogfile.slashem"): ("slashem", "\t",
                                            "em.slashem.me/userdata/{name}/dn36/dumplog/{starttime}.dn36.txt")}
    # livelogs is actually just the challenge log at this point.
    livelogs  = {filepath.FilePath("/var/www/hardfought.org/challenge/dn36_log"): ("", ":")}

    # Forward events to other bots at the request of maintainers of other variant-specific channels
    #forwards = {"hardfought" : [],
    #            "slashem" : []} 
    # Stats for hourly/daily spam

    looping_calls = None
    commands = {}

    def initStats(self, statset):
        self.stats[statset] = { "race"   : {}, 
                                "role"   : {},
                                "gender" : {},
                                "align"  : {},
                                "points" : 0,
                                "turns"  : 0,
                                "games"  : 0,
                                "ascend" : 0
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

        #stats for hourly/daily spam
        self.stats = {}
        self.initStats("hour")
        self.initStats("day")
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

        # sequentially read xlogfiles from beginning to pre-populate lastgame data.
        for filepath in self.xlogfiles:
            with filepath.open("r") as handle:
                for line in handle:
                    delim = self.logs[filepath][2]
                    game = self.logs[filepath][4](line, delim)
                    game["server"] = self.logs[filepath][1]
                    game["dumpfmt"] = self.logs[filepath][3]
                    for line in self.logs[filepath][0](game,False):
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

    
    def tweet(self, message):
        if TWIT: self.twit.statuses.update(status=message)

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
        message = re.sub(r'\x03\d\d,\d\d', '', message) # fg,bg pair
        message = re.sub(r'\x03\d\d', '', message) # fg only
        message = re.sub(r'[\x03\x0f]', '', message) # end of colour
        if time.strftime("%d") != self.logday: self.logRotate()
        self.chanLog[channel].write(time.strftime("%H:%M ") + message + "\n")
        self.chanLog[channel].flush()

    # wrapper for "msg" that logs if msg dest is channel
    # Need to log our own actions separately as they don't trigger events
    def msgLog(self, replyto, message):
        if replyto in CHANNELS:
            self.log(replyto, "<" + self.nickname + "> " + message)
        self.msg(replyto, message)

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

    # Hourly/daily stats 
    def spamStats(self,period):
        # formatting awkwardness
        stat1str = { "turns"  : " turns were played in games that ended.",
                     "points" : " points were scored in games that ended.",
                   }
        # weighted randomness
        stat1 = random.choice(["turns", "points"])
        stat2 = random.choice(["role"] * 5 + ["race"] * 3 + ["align"] * 2 + ["gender"])
        # Find whatever thing from the list above had the most games, and how many games it had
        maxStat2 = dict(zip(["name","number"],max(self.stats[period][stat2].iteritems(), key=lambda x:x[1])))
        for c in SPAMCHANNELS:
            self.msgLog(c, "In the last " + period + " {games} games ended, with {ascend} ascensions.".format(**self.stats[period]))
            self.msgLog(c, str(self.stats[period][stat1]) + stat1str[stat1])
            self.msgLog(c, "The most popular " + stat2 + " was {name} with {number} games.".format(**maxStat2))


    def hourlyStats(self):
        nowtime = datetime.now()
        game_on =  (nowtime > self.ttime["start"]) and (nowtime < self.ttime["end"])
        for c in SPAMCHANNELS:
            # only spam channels if other people are have been talking here
            # Don't be a Nigel. We're cooler than that.
            if self.activity[c] > ACT_THRESHOLD or game_on: 
                self.doTime("",c,"")
                self.activity[c] = 0
        if not game_on: return

        if now.hour == 0:
            self.spamStats("day")
            self.initStats("day")
        else:
            self.spamStats("hour")
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
            cd["countdown"] = (self.ttime[event] - datetime.now()) + timedelta(seconds=0.5)
            if cd["countdown"] > timedelta(0):
                return cd
        return cd

    # implement commands here
    def doPing(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "Pong! " + " ".join(msgwords[1:]))

    def doTime(self, sender, replyto, msgwords):
        self.respond(replyto, sender, time.strftime("The time is %H:%M:%S(%Z) on %A, %B %d, %Y"))
        timeLeft = self.countDown()
        if timeLeft["countdown"] <= timedelta(0):
            self.respond(replyto, sender, "The tournament is OVER!")
            return 
        strcountdown = str(timeLeft["countdown"]).split(".")[0] # no microseconds
        self.respond(replyto, sender, "The tournament {event}s in ".format(**timeLeft)
                                      + strcountdown + ".")

    def doScoreboard(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "Please see " + self.scoresURL + " for the current standings.")

    def doServers(self, sender, replyto, msgwords):
        for s in self.servers:
            self.respond(replyto,sender, " : ".join(s))
        
    def doHelp(self, sender, replyto, msgwords):
        self.respond(replyto, sender, "&ping    - ping!\n"
                                    + "&time    - Get time remaining\n"
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
        if self.startscummed(game): return

        lname = game["name"].lower()
        var = game["server"].lower() # var is server, formerly variant.

        dumplog = game.get("dumplog",False)
        # Need to figure out the dump path before messing with the name below
        dumpfile = (self.dump_file_prefix + game["dumpfmt"]).format(**game)
#        if TEST or os.path.exists(dumpfile): # dump files may not exist on test system
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
        # collect hourly/daily stats for games that actually ended now(ish)
        for period in ["hour","day"]:
            self.stats[period]["games"] += 1
            for tp in ["turns","points"]:
                self.stats[period][tp] += game[tp]
            for rrga in ["role","race","gender","align"]:
                self.stats[period][rrga][game[rrga]] = self.stats[period][rrga].get(game[rrga],0) + 1
            if game["death"] == "ascended":
                self.stats[period]["ascend"] += 1

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
                   "{points} points, {death}{ascsuff}").format(**game)

    # actually "challenge" log reporting
    def livelogReport(self, event):
       print event
       actioned = { "accept": "accepted", "success": "completed", "ignore": "ignored" }
       event["acted"] = actioned[event["action"]]
       yield ("CHALLENGE " + event["acted"].upper() + "! {player} {acted} the {challenge} challenge.".format(**event))

    def connectionLost(self, reason=None):
        if self.looping_calls is None: return
        for call in self.looping_calls.itervalues():
            call.stop()

    def logReport(self, filepath):
        with filepath.open("r") as handle:
            handle.seek(self.logs_seek[filepath])

            for line in handle:
                delim = self.logs[filepath][2]
                game = self.logs[filepath][4](line, delim)
                if self.logs[filepath][1]: game["server"] = self.logs[filepath][1]
                if self.logs[filepath][3]: game["dumpfmt"] = self.logs[filepath][3]
                for line in self.logs[filepath][0](game):
                    for c in CHANNELS: self.msgLog(c, line)
                    # Announce on twitter!!
                    self.tweet(line)
#                    for fwd in self.forwards[game["variant"]]:
#                        self.msg(fwd, line)

            self.logs_seek[filepath] = handle.tell()

if __name__ == "__builtin__":
    f = protocol.ReconnectingClientFactory()
    f.protocol = DeathBotProtocol
    application = service.Application("DeathBot")
    deathservice = internet.SSLClient(HOST, PORT, f,
                                      ssl.ClientContextFactory())
    deathservice.setServiceParent(application)
