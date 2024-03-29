from .sazblackjack import SazBlackjack

try:
    from prettytable import PrettyTable
    requirementsSuccess = True
except:
    requirementsSuccess = False


async def setup(bot):
    if requirementsSuccess:
        await bot.add_cog(SazBlackjack(bot))
    else:
        raise RuntimeError("You are missing requirements. Please run:\n"
                           "`pip install prettytable`")
