#!/bin/echo This file is not meant to be executable:

import os
import sys
import json
import os.path

def load_json(path):
    """Load a json file given a path"""
    return json.load(open(path, encoding="utf-8"))

def save_json_to_fd(fd, value):
    """Save a readable json value into the given file descriptor."""
    json.dump(value, fd, indent=8, separators=(',', ': '), ensure_ascii=False)

def save_json(path, value):
    """Save a readable json value into the given path."""
    save_json_to_fd(open(path, 'w', encoding="utf-8"), value)

if sys.version_info < (3, 7):
    # a note about dicts and load/save_json:
    # Since Python 3.6, the CPython dict's new clever implementation comes with
    # the guarantees that the order of iteration is the order of insertion.
    # Python 3.7 explicitely state it in it's documentation.
    print("""Your python version is TOO OLD: %s

Please upgrade to Python 3.6 or later.  This program will still work, but the
result will be unpredicable, which will cause problem when attempting to apply
version control on the results or even when manually editing JSON files with
another editor."""%sys.version, file=sys.stderr)

def sort_dict(input_dict, recurse=False):
    """Return a dict with the same content as input_dict, but sorted.

    If recurse is true, then if the dict value is a dict, we also sort this
    dict, recusively."""
    res = {}
    for key, value in sorted(input_dict.items(), key=lambda i: i[0]):
        if recurse is True and isinstance(value, dict):
            value = sort_dict(value, True)
        res[key] = value
    return res

def drain_dict(input_dict):
    """Iterate over the dict's items, draining the dict in the process.

    this aims at preserving the iteration order of the dict."""
    # turn the dict into an array
    # this should be fast, with references
    array = list(input_dict.items())
    input_dict.clear()
    array.reverse()
    while array:
        yield array.pop()

def walk_json_inner(json, dict_path=None, reverse_path=None):
    if dict_path is None:
        dict_path = []
    if reverse_path is None:
        reverse_path = []
    if (yield json, dict_path, reverse_path) is False:
        # This simplifies the callers, allowing them to not handle
        # the return value of send()
        yield None
        return
    if isinstance(json, dict):
        iterable = json.items() # not sorted
    elif isinstance(json, list):
        iterable = ((str(i), value) for i, value in enumerate(json))
    else:
        return
    reverse_path.append(json)
    for key, value in iterable:
        dict_path.append(key)
        yield from walk_json_inner(value, dict_path, reverse_path)
        popped_key = dict_path.pop()
        assert popped_key is key
    popped_json = reverse_path.pop()
    assert popped_json is json

def walk_json_filtered_inner(json, filterfunc):
    if filterfunc(json):
        yield json, [], []
        return
    if isinstance(json, dict):
        iterable = json.items()
    elif isinstance(json, list):
        iterable = enumerate(json)
    else:
        return
    for key, value in iterable:
        inneriter = walk_json_filtered_inner(value, filterfunc)
        for to_yield, rev_dict_path, rev_reverse_path in inneriter:
            rev_dict_path.append(str(key))
            rev_reverse_path.append(json)
            yield to_yield, rev_dict_path, rev_reverse_path


def walk_json_filtered(json, filterfunc):
    iterator = walk_json_filtered_inner(json, filterfunc)
    for json, rev_dict_path, rev_reverse_path in iterator:
        rev_dict_path.reverse()
        rev_reverse_path.reverse()
        yield json, rev_dict_path, rev_reverse_path

def walk_json_for_langlabels(json, lang_to_check):
    filter_func = lambda ll: (ll.__class__ is dict and lang_to_check in ll)
    yield from walk_json_filtered(json, filter_func)

def walk_langfile_json(json, lang):
    for value, dict_path, reverse_path in walk_json_inner(json):
        if len(dict_path) == 1:
            continue
        elif not isinstance(value, str):
            continue
        yield {lang: value}, dict_path, reverse_path

def walk_files(base_path, sort=True):
    for dirpath, subdirs, filenames in os.walk(base_path, topdown=True):
        subdirs.sort()
        for name in sorted(filenames) if sort else filenames:
            if not name.endswith('.json'):
                continue
            usable_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(usable_path, base_path)
            yield usable_path, rel_path

def walk_assets_for_translatables(base_path, orig_lang,
                                  path_filter=lambda x: True):
    for usable_path, rel_path in walk_files(base_path):
        file_path = rel_path.split(os.sep)
        if not path_filter(file_path):
            continue
        json = load_json(usable_path)
        if rel_path.startswith("lang"):
            if orig_lang not in rel_path:
                continue
            iterable = walk_langfile_json(json, orig_lang)
        else:
            iterable = walk_json_for_langlabels(json, orig_lang)
        for value, dict_path, reverse_path in iterable:
            yield value, (file_path, dict_path), reverse_path

def get_data_by_dict_path(json, dict_path, include_reverse=False):
    reverse_path = []
    for component in dict_path:
        if include_reverse:
            reverse_path.append(json)
        if isinstance(json, list):
            try:
                json = json[int(component)]
            except:
                return None
        else:
            json = json.get(component)
            if json is None:
                return None
    if include_reverse:
        return json, reverse_path
    return json


def serialize_dict_path(file_path, dict_path):
    # FIXME: we need a better encoding maybe. Look for RFC 6901
    # eg: escape / in keys with \, escape \ with \ as well, and find
    # a way to handle json files not having a .json extension.
    assert file_path[-1][-5:] == ".json"
    return "%s/%s"%("/".join(file_path), "/".join(dict_path))

def unserialize_dict_path(dict_path_str):
    splitted = dict_path_str.split('/')
    for index, value in enumerate(splitted):
        if value.endswith('.json'):
            return (splitted[:index+1], splitted[index+1:])
    raise ValueError("cannot unserialize that")



def get_assets_path(path):
    realpath = os.path.realpath(path)
    realsplit = realpath.split(os.sep)
    try:
        index = realsplit.index("assets")
    except ValueError:
        maybe = os.path.join(path, "assets")
        if os.path.isdir(maybe):
            return maybe
        raise ValueError("could not find game assets."
                         " Searched in %s and %s/assets"%(path, path))
    else:
        return path + ("%s.."%os.sep) * (len(realsplit) - index - 1)

class sparse_dict_path_reader:
    def __init__(self, gamepath, default_lang):
        self.base_path = os.path.join(get_assets_path(gamepath), "data")
        self.last_loaded = None
        self.last_data = None
        self.default_lang = default_lang

    def load_file(self, file_path):
        if self.last_loaded == file_path:
            return None
        usable_path = os.path.join(self.base_path, os.sep.join(file_path))
        try:
            self.last_data = load_json(usable_path)
        except Exception as ex:
            print("Cannot find game file:", "/".join(file_path), ':', str(ex))
            self.last_data = {}
        self.last_loaded = file_path
        return self.last_data

    def get_complete(self, file_path, dict_path):
        """return complete data given a file_path/dict_path

        return something with the same format as
        walk_assets_for_translatables(), note that first return may be None"""
        self.load_file(file_path)
        ret = get_data_by_dict_path(self.last_data, dict_path,
                                    include_reverse=True)
        reverse = ()
        if ret is not None:
            ret, reverse = ret
            if file_path[0] == 'lang':
                ret = {self.default_lang: ret}
        return (ret, (file_path, dict_path), reverse)


    def get_complete_by_str(self, file_dict_path_str):
        file_path, dict_path = unserialize_dict_path(file_dict_path_str)
        return self.get_complete(file_path, dict_path)

    def get(self, file_path, dict_path):
        self.load_file(file_path)
        ret = get_data_by_dict_path(self.last_data, dict_path)
        if file_path[0] != "lang" and ret is not None:
            assert isinstance(ret, dict)
            return ret.get(self.default_lang)
        return ret

    def get_str(self, file_dict_path_str):
        return self.get(*unserialize_dict_path(file_dict_path_str))

class string_cache:
    """reads a big json file instead of browsing the game files.

    also provides the same interface as sparse_dict_path_reader, except it
    has no reverse path, of course, but passes the extra fields instead"""
    def __init__(self, default_lang=None):
        self.data = {}
        self.default_lang = default_lang
    def load_from_file(self, filename, langs=None):
        # a streaming parser would be ideal here... but this will do.
        self.data = load_json(filename)
        if langs is not None:
            self.filter_lang(langs)
    def filter_lang(self, langs):
        for entry in self.data.values():
            langlabel = entry["langlabel"]
            for key in list(langlabel.keys()):
                if key not in langs:
                    del langlabel[key]
    def iterate_drain(self):
        for file_dict_path_str, entry in drain_dict(self.data):
            splitted_path = unserialize_dict_path(file_dict_path_str)
            yield entry["langlabel"], splitted_path, file_dict_path_str, entry
    def iterate(self):
        for file_dict_path_str, entry in self.data.items():
            file_path, dict_path = unserialize_dict_path(file_dict_path_str)
            yield entry["langlabel"], (file_path, dict_path), entry

    def add(self, dict_file_path_str, lang_label_like, extra=None):
        entry = {"langlabel": lang_label_like}
        if extra is not None:
            entry.update(extra)
        self.data[dict_file_path_str] = entry
    def save_into_file(self, filename):
        save_json(filename, self.data)
    # sparse_dict_path_reader
    def get_complete(self, file_path, dict_path):
        file_dict_path_str = serialize_dict_path(file_path, dict_path)
        ret = self.data.get(file_dict_path_str, {})
        return (ret.get("langlabel"), (file_path, dict_path), ret)
    def get_complete_by_str(self, file_dict_path_str):
        file_path, dict_path = unserialize_dict_path(file_dict_path_str)
        ret = self.data.get(file_dict_path_str, {})
        return (ret.get("langlabel"), (file_path, dict_path), ret)
    def get(self, file_path, dict_path):
        return self.get_str(serialize_dict_path(file_path, dict_path))
    def get_str(self, file_dict_path_str):
        ret = self.data.get(file_dict_path_str)
        if ret is None:
            return None
        return ret["langlabel"].get(self.default_lang)

def transform_file_or_dir(input_path, output_path):
    """Browse all files in input_file and transform them into output_path.

    e.g. you can reimplement cp -r with:
    for a,b,c in transform_file_or_dir(arg1, arg2):
        open(a, "w").write(open(b).read())

    It supports the following cases:
    input | output | result
    -----------------------
    file  | file   | yield input, output, None
    file  | dir    | yield input, output + basename(input), None
    dir   | dir    | will walk the input directory, and
                     yield (input_file, output_file, relative_path) for each
                     found file.  This will also recreate the output directory
                     along the way.
    dir   | file   | will fail.
    """
    if os.path.isfile(input_path):
        if os.path.isdir(output_path):
            filename = os.path.basename(input_path)
            output_path = os.path.join(output_path, filename)
        yield input_path, output_path, None
    elif os.path.isdir(input_path):
        olddirpath = None
        for usable_path, rel_path in walk_files(input_path):
            dirpath = os.path.dirname(rel_path)
            if olddirpath != dirpath:
                olddirpath = dirpath
                os.makedirs(os.path.join(output_path, dirpath), exist_ok=True)
            yield usable_path, os.path.join(output_path, rel_path), rel_path
    else:
        raise ValueError("input '%s' does not exist"%input_path)
