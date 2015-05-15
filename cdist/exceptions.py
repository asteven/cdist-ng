class CdistError(Exception):
    """An exception that Cdist can handle and show to the user.
    """
    pass


class ConflictingTagsError(CdistError):
    """An exception that is raised if the user has passed conflicting tags
    to a command.
    """
    pass


class IllegalObjectIdError(CdistError):
    """Raised if cdist is passed an illegal object id.
    """
    def __init__(self, object_id, message='Illegal object id'):
        self.object_id = object_id
        self.message = message

    def __str__(self):
        return '%s: %s' % (self.message, self.object_id)


class MissingRequiredEnvironmentVariableError(CdistError):
    """Raised if an expected enironment variable is not defined.
    """
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "The required environment variable '%s' is not defined." % self.name

