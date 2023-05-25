from .redditvideo import RedditVideo
try:
    from bs4 import BeautifulSoup as BS4
    import aiohttp
    import shutil
    import re
    import sys
    import subprocess
    import os
    import aiofile
    requirementsSuccess = True
    if not shutil.which('youtube-dl'):
        print("can't find youtube-dl")
        print(os.environ)
        requirementsSuccess = False
except Exception as e:
    print(e)
    requirementsSuccess = False


async def setup(bot):
    if requirementsSuccess:
        await bot.add_cog(RedditVideo(bot))
    else:
        raise RuntimeError(
            "You are missing requirements. Please run:\n"
            "`pip3 install beautifulsoup4`\n`pip3 install youtube-dl`\n`pip3 install aiofile`"
        )
