
def comma_delimited_string_to_set(ctx, param, value):
    """A click option callback that flattens a list of comma seperated strings
    into one list of options.
    """
    _list = []
    for v in value:
        _list.extend(v.split(','))
    return set(_list)


