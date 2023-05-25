import re

import aiohttp
import asyncio
import math
from redbot.core import commands
from redbot.core import Config
from discord.ext import tasks
import discord
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta
import json
from datetime import datetime
from bs4 import BeautifulSoup

defaultFeedInfo = {
    "Name": "",
    "URL": "",
    "Tweets": {},
    "AlertWords": [],
    "Channel": "",
    "Version": 0.10
}

defaultTweetInfo = {
    "Text": "",
    "Image": ""
}


class FeedsError(Exception):
    pass


class FeedAlreadyExists(FeedsError):
    pass


class FeedDoesNotExist(FeedsError):
    pass


class WordNotAlerted(Exception):
    pass


class FeedsData(commands.Cog):
    """Holds all the profile data"""
    jsonVersion = 0.2

    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=42928372123)
        self.config.register_global(Feeds={})
        #print('Loading feeds')
        #self.feeds = dataIO.load_json(file_path)
        #print('Feeds loaded')
        self.bot = bot
        #await self.update_all_feeds()

    async def create_feed(self, name, URL, channel):
        path = self.feeds

        feed_id = "{}{}".format(name, channel.id)

        if feed_id in path:
            raise FeedAlreadyExists()

        default_feed = deepcopy(defaultFeedInfo)
        path[feed_id] = default_feed
        path[feed_id]["URL"] = URL
        path[feed_id]["Name"] = name
        path[feed_id]["Version"] = self.jsonVersion
        path[feed_id]["Channel"] = channel.id
        await self.save_feeds()
        retFeed = path[feed_id]
        return retFeed

    async def remove_feed(self, feedPath, channel):
        try:
            await self.get_feed(feedPath, channel)
        except:
            raise FeedDoesNotExist()
        feed_id = "{}{}".format(feedPath, channel.id)
        self.feeds.pop(feed_id)
        await self.save_feeds()

    async def save_feeds(self):
        await self.config.Feeds.set(self.feeds)

    async def load_feeds(self):
        await self.bot.wait_until_red_ready()
        self.feeds = await self.config.Feeds()
        print("TweetMonitor loaded")

    async def get_all_feeds(self):
        feedRet = self.feeds
        return feedRet

    async def get_feed(self, name, channel):
        feed_id = "{}{}".format(name, channel.id)
        if feed_id in self.feeds:
            ret = self.feeds[feed_id]
            if ret["Version"] < self.jsonVersion:
                await self.update_json(ret)
            return ret
        else:
            raise FeedDoesNotExist()

    async def update_all_feeds(self):
        for feed in self.feeds:
            f = self.feeds[feed]
            if f["Version"] < self.jsonVersion:
                await self.update_json(f)

    async def add_alert_word(self, feed, word):
        feed['AlertWords'].append(word)
        await self.save_feeds()

    async def del_alert_word(self, feed, word):
        try:
            feed['AlertWords'].remove(word)
            await self.save_feeds()
        except:
            raise WordNotAlerted()

    async def update_json(self, path):
        # call all relevant patches
        if path['Version'] == 0.1:
            self.convert_json01_to_json02(path)
        await self.save_feeds()

    def convert_json01_to_json02(self, path):
        if 'AlertWords' not in path:
            path['AlertWords'] = []

    async def get_webresponse(self, url):
        text = ''
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                text = await response.text()
        return text

    async def get_soup(self, url, name):
        base_url = "https://twitter.com/i/search/timeline?f=tweets&vertical=news&q=from%3A{}%20include%3Anativeretweets&src=typd&&include_available_features=1&include_entities=1&max_position=&reset_error_state=false"
        new_url = base_url.format(url.replace('https://twitter.com/', ''))
        text = await self.get_webresponse(new_url)
        jsons = json.loads(text)
        soup = BeautifulSoup(jsons['items_html'], "html.parser")
        return soup

    async def get_tweets(self, feed):
        return await self.get_soup(feed['URL'], feed['Name'])

    async def get_feed_tweets(self, shouldPrint, feed):
        soup = await self.get_tweets(feed)
        for tweet_container in reversed(soup.find_all(attrs={"class": "tweet"})):
            # initialise variables that are needed
            context_tag = None
            author = None
            content = None
            iframe = None
            card_image = None
            card_container = None
            card_content = None
            card_text = None
            text_url = None

            tweet_id = tweet_container['data-tweet-id']
            tweet_permalink = tweet_container.find(
                attrs={"class": "js-permalink"})
            tweet_context = tweet_container.find(
                attrs={"class": "tweet-context"})
            tweet_quote = tweet_container.find(
                attrs={"class": "QuoteTweet-authorAndText"})
            tweet_text = tweet_container.find(
                attrs={"class": "js-tweet-text-container"})
            tweet_card = tweet_container.select_one(
                "div.card2.js-media-container")
            if tweet_context:
                context_tag = soup.new_tag('p')
                context_tag.string = "Retweeted "
                tweet_user = str.strip(tweet_container.find(
                    attrs={"class": "stream-item-header"}).find(attrs={"class": "username"}).text)
                context_tag.string += tweet_user
                tweet_text.insert(1, context_tag)

            if tweet_quote:
                author = str.strip(tweet_quote.find(
                    attrs={"class": "username"}).text)
                content = str.strip(tweet_quote.find(
                    attrs={"QuoteTweet-text"}).text)
                quote_tag = soup.new_tag('p')
                quote_tag.string = f"\n>{author}\n>{content}"
                tweet_text.append(quote_tag)

            if tweet_card:
                iframe = tweet_card.find(
                    attrs={"class": "js-macaw-cards-iframe-container"})
                if iframe:
                    iframe_url = iframe.get('data-full-card-iframe-url')
                    full_url = 'https://twitter.com'
                    full_url += iframe_url
                    soup2 = await self.get_soup(full_url, 'iframe ' + feed['Name'])
                    card_image = soup2.find(
                        attrs={"class": "tcu-imageWrapper"})
                    card_container = soup2.find(
                        attrs={"class": "TwitterCard-container"})
                    card_content = soup2.find(
                        attrs={"class": "SummaryCard-content"})
                    if card_container is not None and card_content is not None:
                        card_text = card_content.find("p")
                        dest_tag = soup.new_tag('p')
                        text_url = card_container.get('href')

                        if card_text:
                            card_tag = soup.new_tag('p')
                            card_tag.string = card_text.text
                            tweet_text.append(card_tag)

                        if not text_url:
                            text_url = card_container.find('a').get('href')
                        if text_url:
                            dest_tag.string = text_url
                            tweet_text.append(dest_tag)

            # need to get rid of the gross a href
            try:
                for a in tweet_text.find_all('a', attrs={"class": "u-hidden"}):
                    a.extract()
            except:
                pass

            if card_image:
                img_tag = card_image.find('img')
                if img_tag:
                    tweet_img = card_image
                else:
                    tweet_img = None
                    print(f'card_image not found')
            else:
                tweet_img = tweet_container.find(
                    attrs={"class": "js-adaptive-photo"})

            if not tweet_img:
                tweet_img = None
            if tweet_id not in feed['Tweets']:
                await self.save_tweet(feed, tweet_id, tweet_text,
                                tweet_img)
                if shouldPrint:
                    await self.print_tweet(feed, tweet_id)

    async def print_tweet(self, feed, tweet_id):
        tweet = feed['Tweets'][tweet_id]
        channel = self.bot.get_channel(int(feed['Channel']))
        alert_words = feed['AlertWords']
        await channel.send("`New Tweet from: {}\n=========================================`".format(feed['URL']))
        if any(word.casefold() in tweet['Text'].casefold() for word in alert_words):
            await channel.send("ALERT {}".format("@everyone"))
        await channel.send("```{}```".format(tweet['Text']))
        if tweet['Image']:
            embed = discord.Embed(title=None, description=None)
            embed.set_image(url=tweet['Image'])
            await channel.send('', embed=embed)

    async def save_tweet(self, feed, tweet_id, tweet_text, tweet_img):
        defaultTweet = deepcopy(defaultTweetInfo)
        feed['Tweets'][tweet_id] = defaultTweet
        text = ""
        for p in tweet_text.find_all('p'):
            text += p.text + "\n"
        feed['Tweets'][tweet_id]['Text'] = text
        if tweet_img:
            feed['Tweets'][tweet_id]['Image'] = tweet_img.img['src']
        else:
            feed['Tweets'][tweet_id]['Image'] = ""
        await self.save_feeds()


class TweetMonitor(FeedsData):

    def __init__(self, bot):
        self.bot = bot
        super().__init__(self.bot)
        init = bot.loop.create_task(super().load_feeds())
        init.add_done_callback(self.add_new_tweets_task)
#        @self.bot.event
#        async def on_ready():
#            await super(TweetMonitor,self).load_feeds()
#            self.add_new_tweets_task
#            print('TWM: ready')


    def add_new_tweets_task(self, task):
        try:
            if not self.cycleTask.done():
                return
        except:
            pass

        self.cycleTask = self.bot.loop.create_task(self.get_new_tweets(True))
        print("TweetMonitor started")


    @commands.group(pass_context=True, no_pm=False, aliases=["twm"])
    async def tweetmonitor(self, ctx):
        """Tweet Monitor Commands"""

        if ctx.invoked_subcommand is None:
            pass
            #await send_cmd_help(ctx)

    @tweetmonitor.command(name="print", pass_context=True, hidden=False)
    async def print(self, ctx, *params):
        """Prints all tweets for a given feed"""

        if len(params) < 2:
            await ctx.send("Invalid parameters.\nUSAGE: [p]tweetmonitor print <name> <number of messages>")
            return
        try:
            feedPath = await super().get_feed(params[0], ctx.message.channel)
            numPrinted = 0
            for tweet in reversed(feedPath['Tweets']):
                await super().print_tweet(feedPath, tweet)
                numPrinted += 1
                if numPrinted >= int(params[1]):
                    return
        except FeedDoesNotExist:
            await ctx.send("{} is not a valid feed.".format(params[0]))

    @tweetmonitor.command(name="delete", pass_context=True, hidden=False)
    async def delete(self, ctx, *params):
        """Deletes a named feed"""

        if len(params) < 1:
            await ctx.send("Invalid parameters.\nUSAGE: [p]tweetmonitor delete <name>")
            return

        try:
            feedPath = await super().get_feed(params[0], ctx.message.channel)
            await super().remove_feed(params[0], ctx.message.channel)
            await ctx.send("Done. Feed {} is deleted.".format(params[0]))
        except FeedDoesNotExist:
            await ctx.send("{} is not a valid feed.".format(params[0]))

    @tweetmonitor.command(name="add", pass_context=True, hidden=False)
    async def add_feed(self, ctx, *params):
        """Adds a feed to be monitored.\n USAGE: [p]tweetmonitor add <name> <URL> """

        if len(params) < 2:
            await ctx.send("Invalid parameters.\nUSAGE: [p]tweetmonitor add <name> <URL>")
            return

        try:
            feed = await super().create_feed(
                params[0], params[1], ctx.message.channel)
        except Exception as e:
            print(e)
            await ctx.send("That feed already exists!")
            return
        try:
            await super().get_feed_tweets(False, feed)
            await ctx.send("Added to monitored feeds")
        except Exception as e:
            print(e)
            await ctx.send("failed to add feed")

    @tweetmonitor.command(name="addalert", pass_context=True, hidden=False, aliases=["monitorword"])
    async def add_alert(self, ctx, *params):
        """Adds a word to detect and send an alert.\n USAGE: [p]tweetmonitor addalert <feed name> <word> """

        if len(params) < 2:
            await ctx.send("Invalid parameters.\nUSAGE: [p]tweetmonitor addalert <feed name> <word> ")
            return

        try:
            feed = await super().get_feed(params[0], ctx.message.channel)
            await super().add_alert_word(feed, params[1])
            await ctx.send("Added alert on {} to feed {}".format(params[1], params[0]))
        except FeedDoesNotExist:
            await ctx.send("That feed doesn't exist!")

    @tweetmonitor.command(name="delalert", pass_context=True, hidden=False, aliases=["deletealert", "unmonitorword", "removealert", "remalert"])
    async def del_alert(self, ctx, *params):
        """Removes a word alert from a feed.\n USAGE: [p]tweetmonitor delalert <feed name> <word> """

        if len(params) < 2:
            await ctx.send("Invalid parameters.\nUSAGE: [p]tweetmonitor delalert <feed name> <word> ")
            return

        try:
            feed = await super().get_feed(params[0], ctx.message.channel)
            await super().del_alert_word(feed, params[1])
            await ctx.send("Removed alert on {} from feed {}".format(params[1], params[0]))
        except FeedDoesNotExist:
            await ctx.send("That feed doesn't exist!")
        except WordNotAlerted:
            await ctx.send("That word isn't an alert for feed {}".format(params[0]))

    def save(self, _):
        self.bot.loop.create_task(super().save_feeds())

    def cog_unload(self):
        print("unloading")
        try:
            self.cycleTask.add_done_callback(self.save)
            self.cycleTask.cancel()
        except:
            pass

    async def get_new_tweets(self, shouldPrint):
        #await self.bot.wait_until_ready()
        while True:
            try:
                print(f"[{datetime.now()}] - TweetMonitor - Getting feeds")
                feeds_path = await super().get_all_feeds()
                for f in feeds_path:
                    feed = feeds_path[f]
                    await super().get_feed_tweets(shouldPrint, feed)
                    await super().save_feeds()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            finally:
                await asyncio.sleep(60)


def check_files():
    system = {"Feeds": {}}
    f = "data/SazCogs/tweetmonitor/feeds.json"
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, system)


def check_folders():
    if not os.path.exists("data/SazCogs/tweetmonitor"):
        print("Creating data/SazCogs/tweetmonitor folder...")
        os.makedirs("data/SazCogs/tweetmonitor")

