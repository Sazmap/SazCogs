requirementsSuccess = True


try:
    import dateutil
except:
    requirementsSuccess = False


async def setup(bot):
    if requirementsSuccess:
        from .remindme import RemindMe
        await bot.add_cog(RemindMe(bot))
    else:
        raise RuntimeError("You are missing requirements. Please run:\n"
                           "`pip3 install python-dateutil`")
