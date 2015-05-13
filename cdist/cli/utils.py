
class delimited_string_to_set(object):
    """A click option callback that flattens a list of delimiter seperated
    strings into one list of options.

    Usage:

    comma_delimited_string_to_set = delimited_string_to_set(',')
    option = click.Option(('--name',), callback=comma_delimited_string_to_set)
    """
    def __init__(self, delimiter):
        self.delimiter = delimiter

    def __call__(self, ctx, param, value):
        _list = []
        for v in value:
            _list.extend(v.split(self.delimiter))
        return set(_list)

comma_delimited_string_to_set = delimited_string_to_set(',')
space_delimited_string_to_set = delimited_string_to_set(' ')
