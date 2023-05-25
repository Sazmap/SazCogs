import asyncio
import math
import sys
from operator import itemgetter
from redbot.core import commands
from redbot.core import Config
from discord.ext import tasks
from dateutil.relativedelta import relativedelta
import discord
import uuid
import os
import re
import sched
from copy import deepcopy
from datetime import datetime, timedelta, date, time
import random
import json
import time

defaultCoreInfo = {
    "Reminds":{}
}

defaultRemindInfo = {
    "ID": 0,
    "Message": 0,
    "Reply": 0,
    "Time": 0,
    "Channel": 0,
    "Version": 0.1
}

class ReminderError(Exception):
    pass

class ReminderDoesNotExist(ReminderError):
    pass


def timesort(input_tweet):
    dt = datetime.strptime(input_tweet['created_at'],
                           "%a %b %d %H:%M:%S %z %Y")
    return dt

class Sleeper():
    def __init__(self, loop):
        self.loop = loop
        self.task = None
        self.sleep_time = 0
        self.sleeping = False
        self.shuttingDown = False
    
    async def sleep(self, delay, result=None):
        self.sleeping = True
        coro = asyncio.sleep(delay, result=result, loop=self.loop)
        self.task = asyncio.ensure_future(coro)
        retValue = False
        try:
            await self.task
            retValue = True
        except asyncio.CancelledError:
            retValue = False
        finally:
            if self.shuttingDown:
                raise asyncio.CancelledError
            return retValue
    
    def _cancel_sleep_task(self):
        self.task.cancel()

    async def cancel_sleep(self):
        if self.task is not None:
            try:
                self._cancel_sleep_task()
                self.task = None
                self.sleeping = False
            except Exception as e:
                print(f"cancel_sleep exception {e}")

class RemindData(commands.Cog):
    """Holds all the reminder data"""
    jsonVersion = 0.1

    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=4584657128)
        self.config.register_global(Core={})
        self.bot = bot
        self.sleeper = Sleeper(self.bot.loop)
        self.cycleTask = None
        self.sortedReminds = None
        self.reminderReady = True
        self.shuttingDown = False
        init = bot.loop.create_task(self.load_all())
        init.add_done_callback(self.add_cycle_task)

    async def setup_sleeper(self, reminder):
        nextDateTime = datetime.fromisoformat(reminder['Time'])
        currentDateTime = datetime.now()
        dateDifference = nextDateTime - currentDateTime
        self.sleeper.sleep_time = round(dateDifference.total_seconds())

    
    async def main_reminder_loop(self):
        while True:
            #kind of like a lock to prevent the async from getting weird.
            if self.reminderReady:
                # setup variable for use later. Set it to a clearly invalid value
                # so it is obvious whether the reminder grabbing failed or not.
                reminder = None
                try:
                    # This may throw an exception if there's no reminders. 
                    # In that case, sleep 600 seconds.
                    reminder = self.sortedReminds[0]
                    await self.setup_sleeper(reminder)

                except Exception:
                    self.sleeper.sleep_time = 600
                
                try:
                    print(f"[{datetime.now()}] - RemindMe - Sleeping {self.sleeper.sleep_time}",flush=True)
                    toPrint = await self.sleeper.sleep(self.sleeper.sleep_time)
                    # Figure out if we need to print - don't need to print if the sleep was cancelled.
                    if toPrint and reminder:
                        await self.send_reminder(reminder)
                        removed_remind = self.sortedReminds.pop(0)
                        await self.remove_reminder(removed_remind["ID"])
                except asyncio.CancelledError:
                    print("Caught cancelled error in main loop", flush=True)
                    if self.sleeper.shuttingDown:
                        raise
                    else:
                        continue
                except Exception as e:
                    print(f"Main Loop exception other than Cancelled: {e}", flush=True)
                    pass
            else:
                await asyncio.sleep(2)

    def add_cycle_task(self, task):
        try:
            if not self.cycleTask.done():
                return
        except:
            pass

        self.cycleTask = self.bot.loop.create_task(self.main_reminder_loop())
        print("RemindMe started", flush=True)

    async def sort_reminders(self):
        try:
            sorted_dict = {key: value for key, value in sorted(self.reminds.items(), key=lambda item: item[1]['Time'])}
        except Exception as e:
            print(f"Failed to create sorted dict {e}", flush=True)
        #ID is not really relevant any more. Only useful for unique storage and access.
        try:
            self.sortedReminds = [sorted_dict[i] for i in sorted_dict]
        except Exception as e:
            print(f"Failed to create sorted list of reminds {e}", flush=True)

    async def reminder_update_event(self):
        self.reminderReady = False
        await self.sleeper.cancel_sleep()
        try:
            await self.sort_reminders()
        except Exception as e:
            print(f"Exception in reminder_update_event {e}", flush=True)
        self.reminderReady = True

    async def add_reminder(self, message, text):
        try:
            reminder_date = self.parse_time_string(text)
            value = await self.create_reminder(message.author, message, message.reference, message.guild, message.channel, reminder_date)
            return value
        except Exception as e:
            print(f"add_reminder exception: {e}", flush=True)

    def generate_id(self):
        id = uuid.uuid4().urn
        while id in self.reminds:
            id = uuid.uuid4().urn
        return id

    async def create_reminder(self, user, message, reply, guild, channel, time):
        path = self.reminds

        id = self.generate_id()

        default_remind = deepcopy(defaultRemindInfo)
        path[id] = default_remind
        path[id]["ID"] = id
        path[id]["User"] = user.id
        path[id]["Message"] = message.id
        if reply: 
            path[id]["Reply"] = reply.message_id
        path[id]["Time"] = time.isoformat()
        if guild:
            path[id]["Guild"] = guild.id
        path[id]["Channel"] = channel.id
        path[id]["Version"] = self.jsonVersion
        try:
            await self.save_all()
            await self.reminder_update_event()
        except Exception as e:
            print(f"exception in create_reminder {e}", flush=True)
        retPath = path[id]
        return retPath

    async def remove_reminder_helper(self, ID):
        await self.remove_reminder(ID)
        await self.reminder_update_event()

    async def remove_reminder(self, ID):
        try:
            await self.get_remind(ID)
        except:
            raise ReminderDoesNotExist()
        
        self.reminds.pop(ID)
        await self.save_all()

    async def save_all(self):
        try:
            self.core['Reminds'] = self.reminds
            await self.config.Core.set(self.core)
        except Exception as e:
            print(f"error in save_all {e}", flush=True)

    async def load_all(self):
        await self.bot.wait_until_red_ready()
        self.core = await self.config.Core()
        if not self.core.get('Reminds'):
            self.core = deepcopy(defaultCoreInfo)
        self.reminds = self.core['Reminds']
        await self.remove_all_passed_reminds()
        print("RemindMe loaded", flush=True)

    async def remove_all_passed_reminds(self):
        await self.sort_reminders()
        removeRemind = True
        while removeRemind and len(self.sortedReminds) > 0:
            nextDateTime = datetime.fromisoformat(self.sortedReminds[0]['Time'])
            currentDateTime = datetime.now()
            dateDifference = nextDateTime - currentDateTime
            if(round(dateDifference.total_seconds())) < 1:
                removed_remind = self.sortedReminds.pop(0)
                await self.remove_reminder(removed_remind["ID"])
            else:
                removeRemind = False
        await self.save_all()


    async def get_all_config(self):
        coreRet = self.core
        return coreRet

    async def get_remind(self, ID):
        if ID in self.reminds:
            ret = self.reminds[ID]
            if ret["Version"] < self.jsonVersion:
                await self.update_json(ret)
            return ret
        else:
            raise ReminderDoesNotExist()

    async def update_all_vers(self):
        for reminder in self.reminds:
            f = self.reminds[reminder]
            if f["Version"] < self.jsonVersion:
                await self.update_json(f)

    async def update_json(self, path):
        # call all relevant patches
        await self.save_all()

    def time_string_to_relativedelta(self, date_str):
        # second_regex = re.compile(r'(\d+)\s*s(ec)?(ond)(s)?')
        # minute_regex = re.compile(r'(\d+)\s*m(?!o)(in)?(ute)?(s)?')
        # hour_regex   = re.compile(r'(\d+)\s*h(?ou)?(?r)?(s)?')
        # day_regex    = re.compile(r'(\d+)\s*d(ay)?(s)?')
        # week_regex   = re.compile(r'(\d+)\s*w(eek)?(s)?')
        # month_regex  = re.compile(r'(\d+)\s*mo(nth)?(s)?')
        # year_regex   = re.compile(r'(\d+)\s*y(ear)?(s)?')
        full_date_regex = re.compile(
        (r'(((?P<seconds>\d+)\s*s(?:ec)?(?:ond)?(?:s)?)|'
        r'((?P<minutes>\d+)\s*m(?!o)(?:in)?(?:ute)?(?:s)?)|'
        r'((?P<hours>\d+)\s*h(?:ou)?(?:r)?(?:s)?)|'
        r'((?P<days>\d+)\s*d(?:ay)?(?:s)?)|'
        r'((?P<weeks>\d+)\s*w(?:ee)?(?:k)?(?:s)?)|'
        r'((?P<months>\d+)\s*mo(?:nth)?(?:s)?)|'
        r'((?P<years>\d+)\s*y(?:ea)?(?:r)?(?:s)?))'))
        all_parts = [x for x in full_date_regex.finditer(date_str)]
        datetime_parts = {}
        for part in all_parts:
            for name, param in part.groupdict().items():
                if param:
                    if datetime_parts.get(name):
                        datetime_parts[name] += int(param)
                    else:
                        datetime_parts[name] = int(param)
        diff_date = relativedelta(**datetime_parts)
        return diff_date

    # Convert the given string into an ISO date string from now
    def parse_time_string(self, date_str):
        new_date = datetime.now()
        return new_date + self.time_string_to_relativedelta(date_str)

    def date_string_to_pretty_string(self, date_str):
        diff_date = self.time_string_to_relativedelta(date_str).normalized()
        l = []
        for attr in ["years", "months", "days", "leapdays",
                     "hours", "minutes", "seconds", "microseconds"]:
            value = getattr(diff_date, attr)
            if value > 1:
                l.append((value, attr))
            elif value:
                l.append((value, attr[:-1]))
        retStr = ""
        for index, item in enumerate(l):
            retStr += f"{item[0]} {item[1]}"
            if index < len(l) - 1:
                retStr += f", "

        return retStr

    async def send_reminder(self, reminder):
        try:
            channel = self.bot.get_channel(reminder['Channel'])
            if not channel:
                return
            message_id = reminder['Message']
            if reminder['Reply']:
                message_id = reminder['Reply']
            message = await channel.fetch_message(message_id)
            user = self.bot.get_user(reminder['User'])
        except Exception as e:
            print(f"failed to get message {e}", flush=True)
        try:
            await message.reply(f'{user.mention} - Reminding you of this message', mention_author=False)
        except Exception as e:
            print(f"failed to send message {e}", flush=True)
        pass



class RemindMe(RemindData):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(self.bot)

    @commands.command(name="remindme", pass_context=True, no_pm=False, aliases=["rm", "RemindMe", "remind_me"])
    async def remindme(self, ctx, *params):
        """Adds a reminder to be sent.\n USAGE: [p]RemindMe time"""

        if len(params) < 1:
            await ctx.send(
                "Invalid parameters.\nUSAGE: [p]RemindMe <time>")
            return

        message_text = " ".join([str(a) for a in params])
        try:
            new_reminder = await super().add_reminder(ctx.message, message_text)
        except:
            await ctx.send("Failed to add reminder")
            return
        if not new_reminder:
            await ctx.send("Failed to add reminder")
            return
        try:
            reply_message = None
            if ctx.message.reference:
                reply_message = ctx.message.reference.resolved
            if not reply_message:
                reply_message = ctx.message
            await reply_message.reply(f"{ctx.message.author.mention} I will remind you of this message in {self.date_string_to_pretty_string(message_text)}", mention_author=False)
        except Exception as _:
            await ctx.send("failed to add reminder")

    def save(self, _):
        t = self.bot.loop.create_task(super().save_all())
        t.add_done_callback(self.unloaded)

    def unloaded(self, _):
        print("RemindMe unloaded.", flush=True)

    def cog_unload(self):
        print("RemindMe unloading",flush=True)
        try:
            self.sleeper.shuttingDown = True
            self.cycleTask.add_done_callback(self.save)
            self.cycleTask.cancel()
        except Exception as e:
            print(f"Exception: {e}", flush=True)
