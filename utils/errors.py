from discord.ext import commands


# inspiration from lightning https://gitlab.com/lightning-bot/Lightning/-/blob/v3/utils/errors.py

class PermissionFailedError(commands.CommandError):
    def __init__(self, cmd, user_name: str, perm_name: str):
        super().__init__(f"{user_name}, You cannot use this command because you cannot `{perm_name}``.")


class MissingRole(commands.CommandError):
    def __init__(self, user_name: str, role_name: str):
        super().__init__(f"{user_name}, You cannot use this command because you do not have the {role_name} role.")


class SqlError(commands.CommandError):
    def __init__(self, command_name, traceback):
        super().__init__(message=f"""A database error has occurred in `{command_name}` with message:
         traceback: \n```sql\n{traceback}```""")


class LoggingError(commands.CommandError):
    def __init__(self, command_name, guild):
        super().__init__(message=f"""Failed to log {command_name} in {guild.name} check configurations!""")


class UnsetError(commands.CommandError):
    def __init__(self, thing):
        self.thing = thing
        super().__init__(message=f"This {thing} has not been set yet in the database")


class BotOwnerError(commands.CommandError):
    def __init__(self):
        super().__init__(message="Command could not be ran because the user is not a bot owner!")


class MissingStaffRoleOrPerms(commands.CommandError):
    def __init__(self, mod_role: str, perms: list):
        self.mod_role = mod_role
        self.perms = perms
        super().__init__(message=f"Command could not be ran because the user did not have the {mod_role} or the following permissions: {perms}")


class NoStaffRolesSaved(commands.CommandError):
    def __init__(self):
        super().__init__(message="No staff roles stored for this guild")


class UntrustedError(commands.CommandError):
    def __init__(self):
        super().__init__(message="User is not in trusted user list or not staff")
