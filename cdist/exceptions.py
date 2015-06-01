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


class CdistObjectError(CdistError):
    """Something went wrong with an object"""

    def __init__(self, cdist_object, message):
        self.object = cdist_object
        self.message = message


    def __str__(self):
        return '%s: %s (defined at %s)' % (self.object.name, self.message, " ".join(self.object['source']))


class MissingRequiredEnvironmentVariableError(CdistError):
    """Raised if an expected enironment variable is not defined.
    """
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "The required environment variable '%s' is not defined." % self.name


class CircularReferenceError(CdistError):
    """Raised if a circular reference between objects is detected.
    """
    def __init__(self, cdist_object, required_object):
        self.cdist_object = cdist_object
        self.required_object = required_object

    def __str__(self):
        return 'Circular reference detected: %s -> %s' % (self.cdist_object.name, self.required_object.name)


class RequirementNotFoundError(CdistError):
    """Raised if an objects requirement can not be found.
    """
    def __init__(self, requirement):
        self.requirement = requirement

    def __str__(self):
        return 'Requirement could not be found: %s' % self.requirement

