from redbot.core import commands
import discord
import traceback
                
try:
    from bs4 import BeautifulSoup as BS4
    import aiohttp
    import shutil
    import re
    import sys
    import subprocess
    import os
    import aiofile
    import asyncio
    requirementsSuccess = True
    if not shutil.which('youtube-dl'):
        print("can't find youtube-dl")
        print(os.environ)
        requirementsSuccess = False
except Exception as e:
    print(e)
    requirementsSuccess = False


class RedditVideo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.can_start = True
        self.dl_success = False
        self.conv_success = False
        self.failed_size = False
        self.url = ""
        self.file_name = ""
        self.original_file_name = ""
        self.vid_name = ""
        self.download_task = None
        self.convert_task = None

    async def download_vid(self):
        try:
            b = subprocess.run([
                'youtube-dl', f'{self.url}', '-f bestvideo+bestaudio/bestvideo', '-q',
                '-o', f'{self.vid_name}', '--merge-output-format', 'mp4'
            ],
                stdout=sys.stdout,
                stderr=sys.stderr)
        except:
            self.dl_success = False
            return
        self.dl_success = True

    async def convert(self):
        self.failed_size = False
        try:
                await self.status_msg.edit(content="Video is larger than 8MB. Trying to convert.\nPlease wait.")
                new_file_name = re.sub(r'\.mp4', r'.conv.mp4', self.file_name)
                origin_aspectratio = subprocess.getoutput(
                    f'ffprobe -v error -select_streams v\:0 -show_entries stream=display_aspect_ratio -of default=noprint_wrappers=1:nokey=1 "{self.file_name}"'
                )
                origin_aspectratio = origin_aspectratio.split(':')
                origin_aspectratio[:] = [int(s) for s in origin_aspectratio]
                widest_ratio = 0
                if origin_aspectratio[1] > origin_aspectratio[0]:
                    widest_ratio = 1
                preset = 'veryfast'
                new_size = [0, 0]
                new_size[widest_ratio] = self.max_res
                new_size[1 - widest_ratio] = int((
                    self.max_res / origin_aspectratio[widest_ratio]) * origin_aspectratio[1 - widest_ratio])
                while (new_size[widest_ratio] % 2 != 0):
                    new_size[widest_ratio] -= 1
                while (new_size[1 - widest_ratio] % 2 != 0):
                    new_size[1 - widest_ratio] -= 1
                cmdline = f'ffmpeg -y -i "{self.file_name}" -vcodec libx264 -crf 27 -preset {preset} -c\:a copy -s {new_size[0]}x{new_size[1]} "{new_file_name}"'
                p = subprocess.Popen(
                    cmdline, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                b = p.poll()
                while b == None:
                    await asyncio.sleep(5)
                    b = p.poll()
                    #cmdline, shell=True, stdout=sys.stdout, stderr=sys.stderr)
                if b != 0:
                    await self.status_msg.edit(content="I'm sorry. Video conversion failed")
                    self.conv_success = False
                    return
                else:
                    self.file_name = new_file_name
                    if (os.path.getsize(new_file_name) > (8*1000 * 1000)):
                        self.failed_size = True
                        self.conv_success = False
                        return

        except Exception as e:
            print('caught exception:', flush=True)
            print(e)
            traceback.print_exc()
            print("", flush=True)
            conv_success = False
        self.conv_success = True


    def process_download(self, _):
        self.file_name = f'{os.getcwd()}{os.sep}{self.vid_name}.mp4'
        size = os.path.getsize(self.file_name)
        self.original_file_name = self.file_name
        if size > (7.8 * 1024 * 1024):
            self.max_res = 1270
            self.convert_task = self.bot.loop.create_task(self.convert())
            self.convert_task.add_done_callback(self.process_conversion)
        else:
            self.conv_success = True
            self.process_conversion(None)



    async def process_async_conversion(self):
        if self.conv_success:
            await self.status_msg.edit(content="Uploading....")
            try:
                with open(self.file_name, 'rb') as f:
                    fi = discord.File(f, filename=f"{os.path.basename(self.file_name)}")
                    await self.ctx.send( file=fi,
                                    content=f'Video from {self.url}')
                    await self.status_msg.delete()

            except Exception as e:
                await self.ctx.send("Failed to upload file")
                print('caught exception:')
                print(e)
                traceback.print_exc()
                print("", flush=True)
        else:
            if self.failed_size:
                self.file_name = self.original_file_name
                self.max_res = int(self.max_res * 0.75)
                self.convert_task = self.bot.loop.create_task(self.convert())
                self.convert_task.add_done_callback(self.process_conversion)
                return

        if (os.path.exists(self.file_name)):
            os.remove(self.file_name)

        if (os.path.exists(self.original_file_name)):
            os.remove(self.original_file_name)
        self.can_start = True


    def process_conversion(self, _):
        self.bot.loop.create_task(self.process_async_conversion())


    @commands.command(name="redditvideo",
                      pass_context=True,
                      hidden=False,
                      aliases=["rvideo", "rv"])
    async def del_alert(self, ctx, *params):
        """Downloads and uploads a reddit video using youtube-dl\n USAGE: [p]rv <Reddit Video URL>"""

        if len(params) < 1:
            await ctx.send(
                "Invalid parameters.\nUSAGE: [p]rv <Reddit Video URL>")
            return

        if not self.can_start:
            await ctx.send("Sorry. Please wait until the current job is finished before starting a new one.")
            return

        self.status_msg = await ctx.send('Please wait while I fetch the video')
        self.can_start = False
        self.url = params[0]
        self.ctx = ctx
        self.max_res = 1270
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{self.url}') as response:
                    text = await response.text()
                    soup = BS4(text, "html.parser")
            title = soup.find("h1", attrs={"slot":"title"})
            vid_name = ""
            try: 
                vid_name = f'{title.text}'
            except:
                meta = soup.select("meta[property*=title]")
                vid_name = f'{meta[0]["content"]}'
            self.vid_name = re.sub(r' : .*', '', vid_name)
            self.vid_name = re.sub(r'^.* - ', '', self.vid_name)
        except Exception as e:
            await ctx.send("Sorry. An error occurred.")
            print('caught exception:')
            print(e)
            traceback.print_exc()
            print("", flush=True)
            self.can_start = True
            return
        self.download_task = self.bot.loop.create_task(self.download_vid())
        self.download_task.add_done_callback(self.process_download)

    def cog_unload(self):
        try:
            self.download_task.cancel()
            self.download_task = None
        except:
            pass

        try:
            self.convert_task.cancel()
            self.convert_task = None
        except:
            pass

    def __unload(self):
        pass

