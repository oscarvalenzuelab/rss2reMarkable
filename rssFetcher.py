#!/usr/bin/env python
# encoding: utf-8

## idea and original code from from from https://gist.github.com/alexwlchan/01cec115a6f51d35ab26

EMAIL_SMTP = "your.smtp.host.here"
EMAIL_USER = "your.user@your.address"
EMAIL_PASSWD = "your.password"
EMAIL_FROM = "News Service <your.user@your.address>"
KINDLE_EMAIL = "@kindle.com"


PANDOC = "/usr/bin/pandoc"
KINDLE_GEN = "./kindlegen"
FEED_FILE = "feeds.txt"
PERIOD = 12 # hours between RSS pulls

### PYTHON boilerplate
import os
import inspect
import threading

root_folder = os.path.realpath(os.path.abspath(os.path.split(
                inspect.getfile(inspect.currentframe()))[0]))
this_file = os.path.realpath(os.path.abspath(inspect.getfile(
                inspect.currentframe())))
feed_file = os.path.expanduser(FEED_FILE)

### end boilerplate

import collections
from datetime import datetime, timedelta
import time
import pytz
import shutil
import feedparser
import pypandoc
import sys
import time
import codecs


Post = collections.namedtuple('Post', [
    'time',
    'blog',
    'title',
    'author',
    'link',
    'body'
])

def load_feeds():
    """Return a list of the feeds for download.
        At the moment, it reads it from `feed_file`.
    """
    with open(feed_file, 'r') as f:
        return list(f)

def update_start(now):
    """
    Update the timestamp of the feed file. The time stamp is used
    as the starting point to download articles.
    """
    new_now = time.mktime(now.timetuple())
    with open(feed_file, 'a'):
        os.utime(feed_file, (new_now, new_now))

def get_start(fname):
    """
    Get the starting time to read posts since. This is currently saved as 
    the timestamp of the feeds file.
    """
    return pytz.utc.localize(datetime.fromtimestamp(os.path.getmtime(fname)))


def process_entry(entry, blog, START):
    """
    Coerces an entry from feedparser into a Post tuple.
    Returns None if the entry should be excluded.

    If it was published before START date, drop the entry.
    """
    try:
        when = entry['updated_parsed']
    except KeyError:
        try:
            when = entry['published_parsed']
        except KeyError:
            return # Ignore undateable posts

    if when:
        when = pytz.utc.localize(datetime.fromtimestamp(time.mktime(when)))
    else:
        # print blog, entry
        return

    if when < START:
        return

    title = entry.get('title', "Null")

    try:
        author = entry['author']
    except KeyError:
        try:
            author = ', '.join(a['name'] for a in entry.get('authors', []))
        except KeyError:
            author = 'Anonymous'

    link = entry['link']

    try:
        body = entry['content'][0]['value']
    except KeyError:
        body = entry['summary']

    return Post(when, blog, title, author, link, body)

class FeedparserThread(threading.Thread):
    """
    Each one of these threads will get the task of opening one feed 
    and process its entries.
    
    Given an url, starting time and a global list, this thread will
    add new posts to the global list, after processing.

    """

    def __init__(self, url, START, posts):
        threading.Thread.__init__(self)
        self.url = url
        self.START = START
        self.posts = posts
        self.myposts = []

    def run(self):
        feed = feedparser.parse(self.url)
        try:
             blog = feed['feed']['title']
        except KeyError:
             blog = "---"
        for entry in feed['entries']:
             post = process_entry(entry, blog, self.START)
             if post:
                 self.myposts.append(post)
        self.myposts.sort()
        self.posts += self.myposts

def get_posts_list(feed_list, START):
    """
    Spawn a worker thread for each feed. 
    """
    posts = []
    ths=[]
    for url in feed_list:
        th = FeedparserThread(url, START, posts)
        ths.append(th)
        th.start()

    for th in ths:
        th.join()

    ## When all is said and done,
    return posts

def nicedate(dt):
    return dt.strftime('%d %B %Y').strip('0')

def nicehour(dt):
    return dt.strftime('%I:%M&thinsp;%p').strip('0').lower()

def nicepost(post):
    thispost = post._asdict()
    thispost['nicedate'] = nicedate(thispost['time'])
    thispost['nicetime'] = nicehour(thispost['time'])
    return thispost

#<link rel="stylesheet" type="text/css" href="style.css">
html_head=u"""<html>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width" />
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <meta name="apple-mobile-web-app-capable" content="yes" />
<style>
</style>
<title>THE DAILY NEWS</title>
</head>
<body>

"""

html_tail=u"""
</body>
</html>
"""

html_perpost=u"""
    <article>
        <h1><a href="{link}">{title}</a></h1>
        <p><small>By {author} for <i>{blog}</i>, on {nicedate} at {nicetime}.</small></p>
         {body}
    </article>
"""

from subprocess import Popen, PIPE


def do_one_round():
    # get all posts from starting point to now
    now = pytz.utc.localize(datetime.now())
    start = get_start(feed_file)


    print "Collecting posts since %s" % start
    sys.stdout.flush()

    posts = get_posts_list(load_feeds(), start)
    posts.sort()

    print "Downloaded %s posts" % len(posts)
    
    if posts:
        print "Compiling newspaper"
        sys.stdout.flush()

        result = html_head + u"\n".join([html_perpost.format(**nicepost(post)) for post in posts]) + html_tail

        # with codecs.open('dailynews.html', 'w', 'utf-8') as f:
        #     f.write(result)

        print "Creating epub"
        sys.stdout.flush()

        os.environ['PYPANDOC_PANDOC'] = PANDOC
        ofile = "dailynews.epub"
        oofile = "dailynews.mobi"
        pypandoc.convert(result,
            to='epub3',
            format="html",
            outputfile=ofile,
            extra_args=["--standalone",
                        "--epub-cover-image=cover.png",
                    ])

        print "Converting to kindle"
        sys.stdout.flush()
        os.system("%s %s -o %s >/dev/null 2>&1" % (KINDLE_GEN, ofile, oofile) )


        print "Sending to kindle email"
        sys.stdout.flush()


#        send_mail(  send_from=EMAIL_FROM,
#                    send_to=[KINDLE_EMAIL],
#                    subject="Daily News",
#                    text="This is your daily news.\n\n--\n\n",
#                    files=[oofile])                    
                    
                    
        print "Cleaning up."
        sys.stdout.flush()
        os.remove(ofile)
        os.remove(oofile)
    
    print "Finished."
    sys.stdout.flush()
    update_start(now)
    

if __name__ == '__main__':
    while True:
        do_one_round()
        time.sleep(PERIOD*60)


