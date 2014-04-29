'''
    Vimeo plugin for XBMC
    Copyright (C) 2010-2012 Tobias Ussing And Henrik Mosgaard Jensen

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import sys
import urllib
import re
import os.path
import datetime
import time
from xml.dom.minidom import parseString

try: import simplejson as json
except ImportError: import json


class VimeoPlayer():

    def __init__(self):
        self.xbmc = sys.modules["__main__"].xbmc
        self.xbmcgui = sys.modules["__main__"].xbmcgui
        self.xbmcplugin = sys.modules["__main__"].xbmcplugin
        self.xbmcvfs = sys.modules["__main__"].xbmcvfs

        self.settings = sys.modules["__main__"].settings
        self.language = sys.modules["__main__"].language
        self.plugin = sys.modules["__main__"].plugin
        self.dbg = sys.modules["__main__"].dbg
        
        self.common = sys.modules["__main__"].common
        self.utils = sys.modules["__main__"].utils
        self.cache = sys.modules["__main__"].cache
        self.core = sys.modules["__main__"].core
        self.login = sys.modules["__main__"].login
        self.storage = sys.modules["__main__"].storage

    # ================================ Video Playback ====================================
    def playVideo(self, params={}):
        self.common.log("")
        get = params.get
        (video, status) = self.getVideoObject(params)
        if status != 200:
            self.common.log("construct video url failed, contents of video item " + repr(video))
            self.utils.showErrorMessage(self.language(30603), video, status)
            return False

        listitem = self.xbmcgui.ListItem(label=video['Title'], iconImage=video['thumbnail'], thumbnailImage=video['thumbnail'], path=video['video_url'])
        listitem.setInfo(type='Video', infoLabels=video)

        self.common.log("Playing video: " + video['Title'] + " - " + get('videoid') + " - " + video['video_url'])

        self.xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listitem)

        if video.has_key('subs'):
            self.addSubtitles(video['subs'])

        self.storage.storeValue("vidstatus-" + get('videoid'), "7")

    def scrapeVideoInfo(self, params):
        get = params.get
        result = self.common.fetchPage({"link": "http://player.vimeo.com/v2/video/%s/config" % get("videoid")})
        collection = {}
        if result["status"] == 200:
            html = result["content"]
            print repr(html)
            collection = json.loads(html)
        return collection

    def getVideoInfo(self, params):
        self.common.log("")
        get = params.get

        collection = self.scrapeVideoInfo(params)

        video = {}
        video['urls'] = {}

        if collection.has_key("request"):
            video['videoid'] = get("videoid")
            for codec in collection["request"]["files"]["codecs"]:
                for profile in collection["request"]["files"][codec]:
                    if profile not in video['urls']:
                        video['urls'][profile] = collection["request"]["files"][codec][profile]

            if "hd" in video['urls']:
                video['isHD'] = "1"

            if collection["request"].has_key("text_tracks"):
                video['subs'] = {}
                for sub in collection["request"]["text_tracks"]:
                    url = urllib.unquote_plus(sub['url'])
                    i = url.find("http://")
                    if i != -1:
                        video['subs'][sub['lang']] = url[i:]

            video['thumbnail'] = ""
            video['Title'] = ""

            if collection.has_key("video"):
                title = collection["video"].get("title", "No Title")
                title = self.common.replaceHTMLCodes(title)
                video['Title'] = title


        if len(video['urls']) == 0:
            self.common.log("- Couldn't parse API output, Vimeo doesn't seem to know this video id?")
            video = {}
            video["apierror"] = self.language(30608)
            return (video, 303)

        self.common.log("Done")
        return (video, 200)

    def getVideoObject(self, params):
        self.common.log("")
        get = params.get
        
        (video, status) = self.getVideoInfo(params)

        #Check if file has been downloaded locally and use that as a source instead
        if (status == 200 and get("action", "") != "download"):
            path = self.settings.getSetting("downloadPath")
            filename = u''.join(c for c in video['Title'] if c not in self.utils.INVALID_CHARS) + u"-[" + get('videoid') + u"]" + u".mp4"
            path = os.path.join(path.decode("utf-8"), filename)
            try:
                if self.xbmcvfs.exists(path):
                    video['video_url'] = path
                    return (video, 200)
            except:
                self.common.log("attempt to locate local file failed with unknown error, trying vimeo instead")

        get = video.get
        if not video:
            # we need a scrape the homepage fallback when the api doesn't want to give us the URL
            self.common.log("getVideoObject failed because of missing video from getVideoInfo")
            return ("", 500)

        quality = self.selectVideoQuality(params, video)

        if ('apierror' not in video):
            if quality not in video["urls"]:
                self.common.log("No suitable resolution found")
                return (self.language(30607), 303)
            video['video_url'] = video["urls"][quality]["url"]
            self.common.log("Done")
            return (video, 200)
        else:
            self.common.log("Got apierror: " + video['apierror'])
            return (video['apierror'], 303)

    def selectVideoQuality(self, params, video):
        self.common.log("" + repr(params) + " - " + repr(video))
        get = params.get
        vget = video.get

        quality = "sd"
        hd_quality = 0
        
        if get("action") == "download":
            hd_quality = int(self.settings.getSetting("hd_videos_download"))
            if (hd_quality == 0):
                hd_quality = int(self.settings.getSetting("hd_videos"))
        else:
            if (not get("quality")):
                hd_quality = int(self.settings.getSetting("hd_videos"))
            else:
                if (get("quality") == "720p"):
                    hd_quality = 2
                else:
                    hd_quality = 1

        if (hd_quality > 1 and vget("isHD", "0") == "1"):
            quality = "hd"
        
        if hd_quality == 0 and not get("quality") and vget("isHD", "0") == "1":
            return self.userSelectsVideoQuality(params)

        self.common.log("Done")
        return quality

    def userSelectsVideoQuality(self, params):
        items = [("hd", "720p"),("sd", "SD")]
        choices = []
                
        if len(items) > 1:             
            for (quality, message) in items:
                choices.append(message)
    
            dialog = self.xbmcgui.Dialog()
            selected = dialog.select(self.language(30518), choices)

            if selected > -1:
                (quality, message) = items[selected]
                return quality
        
        return "sd"

    def addSubtitles(self, subs={}):
        if len(subs) == 0:
            return

        if not subs.has_key('en'):
            return

        player = self.xbmc.Player()

        i = 0
        while not player.isPlaying():
            i += 1
            self.common.log(u"Waiting for playback to start ")
            time.sleep(1)
            if i > 10:
                break

        player.setSubtitles(subs['en'])
        player.showSubtitles(False)
