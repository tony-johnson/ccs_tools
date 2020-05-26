import datetime
import fnmatch
from string import Template

import numpy as np
import pandas as pd
import pytz
import requests
from IPython.core.display import Javascript, display

DEFAULT_REST_URL = "https://lsst-camera-dev.slac.stanford.edu/CCSWebTrending/rest/"
DEFAULT_SITE = "ir2"


class Channel:
    ''' Represents a single channel as read from the trending tree. A Channel may
    represent a folder with no actual data, or a leaf node with associated trending
    data '''

    def __init__(self, restURL, path, node):
        self.restURL = restURL
        self.path = path
        self.text = node['text']
        self.id = node['id']
        self.data = int(node.get('data')) if 'data' in node else None
        self.hasChildren = node['children']
        self.children = {}

    def full_path(self):
        return self.path + '/' + self.text if self.path else self.text

    def __repr__(self):
        return "Channel (%s (%s) %s)" % (self.full_path(), self.hasChildren, self.data)

    def find(self, name):
        if self.hasChildren and not self.children:
            self.__load_children()
        tokens = name.split('/', 1)
        child = self.children[tokens[0]]
        if len(tokens) == 1:
            return child
        else:
            return child.find(tokens[1])

    def find_all(self, path, leaf_only=True):
        if self.hasChildren and not self.children:
            self.__load_children()
        tokens = path.split('/', 1)
        result = []
        for key, child in self.children.items():
            if fnmatch.fnmatchcase(key, tokens[0]):
                if len(tokens) == 1:
                    if not leaf_only or not child.hasChildren:
                        result.append(child)
                else:
                    result += child.find_all(tokens[1], leaf_only)
        return result

    def ls(self, recursive=False):
        if self.hasChildren and not self.children:
            self.__load_children()
        if recursive:
            l = []
            for key, value in self.children. items():
                l.append(key)
                if value.hasChildren:
                    l.append(value.ls(True))
            return l
        else:
            return self.children.keys()

    def __load_children(self):
        if self.hasChildren and not self.children:
            url = self.restURL
            if id != 0:
                url += "?id=%d" % self.id
            r = requests.get(url)
            r.raise_for_status()
            json = r.json()
            full_path = self.full_path()
            for node in json:
                c = Channel(self.restURL, full_path, node)
                self.children[c.text] = c


class ChannelMapHelper:
    def __init__(self, path, cm):
        self.channels = cm.find_all(path, leaf_only=True)
        if not self.channels:
            raise RuntimeError("Path did not match any leaf nodes: "+path)
        elif len(self.channels) == 1:
            matches = self.channels[0].full_path().split('/')
            self.suggested_title = "/".join(matches[:-1])
            self.suggested_names = matches[-1:]
        else:
            matches = self.channels[0].full_path().split('/')
            for channel in self.channels[1:]:
                fp = channel.full_path()
                tokens = fp.split('/')
                for i, token in enumerate(tokens):
                    if token != matches[i]:
                        matches[i] = "*"
            self.suggested_title = '/'.join(matches)
            names = [""] * len(self.channels)
            for channel_index, channel in enumerate(self.channels):
                fp = channel.full_path()
                tokens = fp.split('/')
                channel_name = []
                for i, token in enumerate(tokens):
                    if matches[i] == "*":
                        channel_name.append(token)
                names[channel_index] += '/'.join(channel_name)
            self.suggested_names = names


class ChannelMap:
    def __init__(self, site=DEFAULT_SITE, restURL=DEFAULT_REST_URL):
        self.root = Channel(restURL+site+"/channels/", "",
                            {'text': '', 'id': 0, 'children': True})

    def find(self, name):
        return self.root.find(name)

    def find_all(self, path, leaf_only=False):
        return self.root.find_all(path, leaf_only)

    def __repr__(self):
        return self.root.__repr__()

    def ls(self, recursive=False):
        return self.root.ls(recursive)


class ChannelDataReader:

    def __init__(self, site=DEFAULT_SITE, restURL=DEFAULT_REST_URL):
        self.restURL = restURL+site

    def read_data(self, ids, names, timePeriod, nBins=100):

        url = "%s?n=%d" % (self.restURL, nBins)
        url += "&t1=%d&t2=%d" % timePeriod.as_millis()
        for id in ids:
            url += "&key=%d" % id
        r = requests.get(url)
        r.raise_for_status()
        json = r.json()
        data = np.array(json['data'])
        df = pd.DataFrame(data=data[:, 1:], index=data[:, 0], columns=names)
        df.index = pd.to_datetime(df.index, unit='ms')
        return df


class TimePeriod:
    epoch = pytz.utc.localize(datetime.datetime.utcfromtimestamp(0))
    @staticmethod
    def to_millis(dt):
        return int((dt-TimePeriod.epoch).total_seconds()*1000)

    def as_millis(self):
        pass

    def as_ccs_string(self):
        pass

    @staticmethod
    def for_range(period):
        if isinstance(period, datetime.timedelta):
            return DeltaTimePeriod(period)
        elif isinstance(period, tuple):
            return StartEndTimePeriod(period[0], period[1])
        else:
            raise RuntimeError(
                "Unsupported argument type for for_range "+period)


class StartEndTimePeriod(TimePeriod):
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def as_millis(self):
        return (TimePeriod.to_millis(self.start), TimePeriod.to_millis(self.end))

    def as_ccs_string(self):
        return "{&quot;start&quot;: %d, &quot;end&quot;: %d}" % (TimePeriod.to_millis(self.start), TimePeriod.to_millis(self.end))


class DeltaTimePeriod(TimePeriod):
    def __init__(self, delta):
        self.delta = delta

    def as_millis(self):
        now = pytz.utc.localize(datetime.datetime.utcnow())
        return (TimePeriod.to_millis(now-self.delta), TimePeriod.to_millis(now))

    def as_ccs_string(self):
        return "%d" % (self.delta.total_seconds() * 1000)


class CCSTrending:
    """A simple jupyter interface to CCS trending"""

    def __init__(self, title=None, data=None, range=datetime.timedelta(days=1), site=DEFAULT_SITE, restURL=DEFAULT_REST_URL):
        self.plots = []
        self.title = title
        self.range = range
        self.restURL = restURL+site
        self.cm = ChannelMap(site=site, restURL=restURL)
        self.dr = ChannelDataReader(site=site, restURL=restURL)

        if data:
            if isinstance(data, str):
                cmh = ChannelMapHelper(data, self.cm)
                # Dont replace user supplied title
                self.title = self.title if self.title else cmh.suggested_title
                for channel, name in zip(cmh.channels, cmh.suggested_names):
                    self.add_channel(channel, name)
            elif isinstance(data, dict):
                for key, value in data.items():
                    self.add_channel(key, value)
            else:
                raise RuntimeError("Unsupported argument type for data "+data)

    @property
    def range(self):
        return self.__range

    @range.setter
    def range(self, range):
        self.__range = TimePeriod.for_range(range)

    def add_channel(self, id, key=None):
        if isinstance(id, int):
            self.plots.append([id, key])
        elif isinstance(id, Channel):
            self.plots.append([id.data, key if key else id.full_path()])
        elif isinstance(id, str):
            channel = self.cm.find(id)
            self.plots.append([channel.data, key if key else channel.text])
        else:
            raise RuntimeError(
                'Unsuppored argument type for add_channel ' + id)

    def add_all(self, channels):
        for channel in channels:
            self.add_channel(channel)

    def __repr__(self):
        return str(self.plots)

    def as_dataframe(self):
        ids = []
        keys = []
        for id, key in self.plots:
            ids.append(id)
            keys.append(key)
        return self.dr.read_data(ids, keys, self.__range)

    def plot(self):
        code = Template('''
            (function(element) {
                new Promise(function(resolve, reject) {
                    var script = document.createElement("script");
                    script.onload = resolve;
                    script.onerror = reject;
                    script.src = "https://lsst-camera-dev.slac.stanford.edu/CCSWebTrending/ccs-trending.js";
                    script.type = "module";
                    document.head.appendChild(script);
                }).then(() => {
		            $$(`<div><trending-controller></trending-controller><trending-plot  style="width:100%;height:300px" title="${title}" restURL="${restURL}" range="${range}">${data}</trending-plot></div>`).appendTo(element);
                });
            })(element);
           ''')

        def output(plots):
            result = ""
            for id, key in plots:
                result += '<trending-data key="%d">%s</trending-data>' % (id, key)
            return result

        js = Javascript(code.substitute(title=self.title, data=output(
            self.plots), range=self.range.as_ccs_string(), restURL=self.restURL))
        display(js)
