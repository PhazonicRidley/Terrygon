from discord.ext import commands


# inspiration from lightning https://gitlab.com/lightning-bot/Lightning/-/blob/v3/utils/errors.py

class permissionFailedError(commands.CommandError):
    def __init__(self, cmd, userName: str, permName: str):
        super().__init__(f"{userName}, You cannot use this command because you cannot `{permName}``.")


class missingRole(commands.CommandError):
    def __init__(self, userName: str, roleName: str):
        super().__init__(f"{userName}, You cannot use this command because you do not have the {roleName} role.")


class sqlError(commands.CommandError):
    def __init__(self, commandName, traceback):
        super().__init__(message=f"""A database error has occurred in `{commandName}` with message:
         traceback: \n```sql\n{traceback}```""")


class loggingError(commands.CommandError):
    def __init__(self, logType, guild):
        super().__init__(message=f"""Failed to log {logType} in {guild.name} check configurations!""")


class unsetError(commands.CommandError):
    def __init__(self, thing):
        self.thing = thing
        super().__init__(message=f"This {thing} has not been set yet in the database")


class botOwnerError(commands.CommandError):
    def __init__(self):
        super().__init__(message="Command could not be ran because the user is not a bot owner!")


class missingStaffRoleOrPerms(commands.CommandError):
    def __init__(self, modrole, perms: list):
        self.modrole = modrole
        self.perms = perms
        super().__init__(
            message=f"Command could not be ran because the user did not have the {modrole} or the following permissions: {perms}")


class noStaffRolesSaved(commands.CommandError):
    def __init__(self):
        super().__init__(message="No staff roles stored for this guild")