from .tweetmonitor import TweetMonitor

try:
    from bs4 import BeautifulSoup
    requirementsSuccess = True
except:
    requirementsSuccess = False


async def setup(bot):
    if requirementsSuccess:
        await bot.add_cog(TweetMonitor(bot))
    else:
        raise RuntimeError("You are missing requirements. Please run:\n"
                           "`pip3 install beautifulsoup4`")
