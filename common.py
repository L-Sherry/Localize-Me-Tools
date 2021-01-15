#!/bin/echo This file is not meant to be executable:

import os
import os.path
import sys
import json
import tags as tagger

def load_json(path):
    """Load a json file given a path.

    Can raise both OSError and json.ValueError (extends ValueError)"""
    try:
        with open(path, encoding="utf-8") as fd:
            return json.load(fd)
    except:
        print("Error while parsing %s:" % path, file=sys.stderr)
        raise

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

def walk_json_inner(json_obj, dict_path=None, reverse_path=None):
    """Walk into a JSON object and yield every sub-object encountered

    Yields (subobject, dict_path, reverse_path), where:
    'subobject' is a sub object
    'dict_path' is an list of indices, of type str or int, such as indexing
    json_obj recursively with them yields 'subobject'.  If e.g. 'dict_path'
    is ["one", 2, "three"], then 'subobject is json_obj["one"][2]["three"]' is
    True.
    'reverse_path' is a list with the same size as 'dict_path', which contains
    all parent objects. reverse_path[0] is always json_obj, and reverse_path[i]
    is reverse_path[i-1][dict_path[i-1]]. Note that 'subobject' is not present
    in 'reverse_path'.

    If a 'subobject' must not be iterated through, then the caller must call
    iterator.send(False).  send() will return None and this function will not
    recurse through 'subobject'.
    """
    if dict_path is None:
        dict_path = []
    if reverse_path is None:
        reverse_path = []
    if (yield json_obj, dict_path, reverse_path) is False:
        # This simplifies the callers, allowing them to not handle
        # the return value of send()
        yield None
        return
    if isinstance(json_obj, dict):
        iterable = json_obj.items() # not sorted
    elif isinstance(json_obj, list):
        iterable = ((str(i), value) for i, value in enumerate(json_obj))
    else:
        return
    reverse_path.append(json_obj)
    for key, value in iterable:
        dict_path.append(key)
        yield from walk_json_inner(value, dict_path, reverse_path)
        popped_key = dict_path.pop()
        assert popped_key is key
    popped_json_obj = reverse_path.pop()
    assert popped_json_obj is json_obj

def walk_json_filtered_inner(json_obj, filterfunc):
    """Internal function to walk and yields JSON sub-objects matching a filter

    Yields the same fields as walk_json_inner(), but 'dict_path' and
    'reverse_path' are reversed.  Use walk_json_filtered() for a non-internal
    interface.
    """
    if filterfunc(json_obj):
        yield json_obj, [], []
        return
    if isinstance(json_obj, dict):
        iterable = json_obj.items()
    elif isinstance(json_obj, list):
        iterable = enumerate(json_obj)
    else:
        return
    for key, value in iterable:
        inneriter = walk_json_filtered_inner(value, filterfunc)
        for to_yield, rev_dict_path, rev_reverse_path in inneriter:
            rev_dict_path.append(str(key))
            rev_reverse_path.append(json_obj)
            yield to_yield, rev_dict_path, rev_reverse_path


def walk_json_filtered(json_obj, filterfunc):
    """Walk into a JSON object and yield sub-objects matching a filter

    Yields the same fields as walk_json_inner(), but only if
    filterfunc(subobject) is trueish.  Note that subobject will not be recursed
    into if filterfunc(subobject) is true.
    """
    iterator = walk_json_filtered_inner(json_obj, filterfunc)
    for json_obj, rev_dict_path, rev_reverse_path in iterator:
        rev_dict_path.reverse()
        rev_reverse_path.reverse()
        yield json_obj, rev_dict_path, rev_reverse_path

def walk_json_for_langlabels(json, lang_to_check):
    """Walk into a JSON object and yield lang labels.

    A object is considered to be a lang label if it contains the lang
    'lang_to_check'.  If lang_to_check is 'en_US', then any object with a
    'en_US' key is considered to be a lang label.

    Yields the following fields (which are the same fields as walk_json_inner):
    (lang_label, dict_path, reverse_path)
    where
    'lang_label' is an object having a lang_to_check key
    'dict_path' is an list of indices, of type str or int, such as indexing
    json_obj recursively with them yields 'subobject'.  If e.g. 'dict_path'
    is ["one", 2, "three"], then 'subobject is json_obj["one"][2]["three"]' is
    True.
    'reverse_path' is a list with the same size as 'dict_path', which contains
    all parent objects. reverse_path[0] is always json_obj, and reverse_path[i]
    is reverse_path[i-1][dict_path[i-1]]. Note that 'lang_label' is not present
    in 'reverse_path'.
    """
    filter_func = lambda ll: (ll.__class__ is dict and lang_to_check in ll)
    yield from walk_json_filtered(json, filter_func)

def walk_langfile_json(json_dict, dict_path, reverse_path):
    """Walk and merge multiple lang files and yield lang labels out of them.

    'json_dict' must be a dictionary of the form:
    {
      "lang1": content_of_langfile1,
      "lang2": content_of_langfile2,
      "lang3": content_of_langfile3
      [...]
    }

    dict_path and reverse_path should be [], or at least have the same size,
    in which case, they will be used as a prefix, but note that they are
    modified in place.

    Yields the following fields (compatible with walk_json_for_langlabels()):
    (fake_lang_label, dict_path, reverse_path)
    where 'fake_lang_label' will contain all key of 'json_dict' where there is
    a string value at 'dict_path'.

    'dict_path' is an list of indices, of type str or int, such as indexing
    json_dict[language] recursively with them yields 'subobject'.  If e.g.
    'dict_path' is ["one", 2, "three"], then
    'fake_lang_label[language] == json_dict[language]["one"][2]["three"]'.
    'reverse_path' is a list with the same size as 'dict_path', which contains
    fake parent objects. reverse_path[0] is always json_dict, and
    reverse_path[i] is a single object having the same format as 'json_dict',
    but for subobjects.  It can be defined as:

    reverse_path[i] = {
        lang1: reverse_path[i-1][lang1][dict_path[i-1]]
        lang2: reverse_path[i-1][lang2][dict_path[i-1]]
        lang3: reverse_path[i-1][lang3][dict_path[i-1]]
        [...]
    }
    Note that 'lang_label' is not present in 'reverse_path'.
    """
    # {a: {x:""}, b: {x:""}, c: {x:""}} -> {x:{a:"", b:"", c:""}}
    strings = {}
    dicts = {}
    for lang, value in list(json_dict.items()):
        if isinstance(value, str):
            strings[lang] = value
        elif isinstance(value, dict):
            for key, subvalue in value.items():
                dicts.setdefault(key, {})[lang] = subvalue
        elif isinstance(value, list):
            # this convert an list into a dict with integer indices...
            # should be enough for everybody
            for i, subvalue in enumerate(value):
                dicts.setdefault(str(i), {})[lang] = subvalue

    if strings:
        yield strings, dict_path, reverse_path
    if not dicts:
        return
    dict_path.append(None)
    reverse_path.append(json_dict)
    for key, value in dicts.items():
        dict_path[-1] = key
        yield from walk_langfile_json(value, dict_path, reverse_path)
    dict_path.pop()
    assert reverse_path.pop() is json_dict

def walk_files(base_path, sort=True):
    """Walk files in a directory for files with a .json extension.

    yield (usable_path, rel_path)
    where 'usable_path' is something that can be passed to open() (i.e. it
    is prepended by base_path), while 'rel_path' is a path relative to
    base_path pointing to the file.

    If sort is True, then iterate files and directory sorted in lexical order,
    for maximum reproducibility.
    """
    for dirpath, subdirs, filenames in os.walk(base_path, topdown=True):
        if sort:
            subdirs.sort()
        for name in sorted(filenames) if sort else filenames:
            if not name.endswith('.json'):
                continue
            usable_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(usable_path, base_path)
            yield usable_path, rel_path

def walk_assets_files(assets_path, sort=True, path_filter=lambda x: True):
    """Walk assets files that may contain texts.

    This actually looks both in assets/data and assets/extension.

    Yield (usable path, file_path) tuples, under the condition that
    path_filter(file_path) is trueish.
    usable_path can be used to open() the file, while file_path is a list of
    relative path components.

    Note that assets/data/extension and assets/extension are aliased."""

    prefix = []
    def iter_files():
        nonlocal prefix
        yield from walk_files(os.path.join(assets_path, "data"), sort)
        prefix = ["extension"]
        yield from walk_files(os.path.join(assets_path, prefix[0]), sort)

    for usable_path, rel_path in iter_files():
        file_path = prefix + rel_path.split(os.sep)
        if not path_filter(file_path):
            continue
        yield usable_path, file_path


def walk_assets_for_translatables(base_path, orig_lang,
                                  path_filter=lambda x: True):
    """Walk the game's assets and yield every lang label or fake lang-labels

    'base_path' is assumed to be a path to an 'assets/data/' directory.
    'orig_lang' is used to find lang labels, and must be a locale name supported
    by the game (e.g. 'en_US').
    If 'path_filter' is given, then only browse files where
    path_filter(file_path) is trueish. file_path is a splitted
    relative path, e.g. ['characters', 'main', 'lea.json']
    for assets/data/characters/main/lea.json.

    Yields the following format:
    (lang_label, (file_path, dict_path), reverse_path)
    'lang_label' is either a lang label read from a json file or one generated
    from multiple lang files.
    'file_path' is a path relative to 'base_path', splitted by the directory
    separator.  If the lang label was generated from multiple lang files, then
    'file_path' will reference the one for the 'orig_lang' language.
    'dict_path' is a list of indices of type str or int, which refers to the
    position of the lang label inside the file (see walk_json_inner for details)
    'reverse_path' are the parents objects of the lang label, ordered by
    descending hierarchy (see walk_json_inner for details)
    """
    def add_file_path(file_path, iterable):
        for value, dict_path, reverse_path in iterable:
            yield value, (file_path, dict_path), reverse_path

    langfiles = {}
    langfile_base = None
    langfile_file_path = None
    def collect_langfiles(base, lang, file_path, json):
        # this assumes that files are sorted. i.e. languages from the same
        # lang file are grouped.
        nonlocal langfiles
        nonlocal langfile_base
        nonlocal langfile_file_path

        if base != langfile_base:

            if langfile_file_path:
                iterator = walk_langfile_json(langfiles, ["labels"], [None])
                yield from add_file_path(langfile_file_path, iterator)
            langfiles.clear()
            langfile_base = base
            langfile_file_path = None
        if lang == orig_lang:
            langfile_file_path = file_path
        if lang:
            langfiles[lang] = json

    for usable_path, file_path in walk_assets_files(base_path, True,
                                                    path_filter):
        json = load_json(usable_path)
        if file_path[0] == "lang":
            langfilename = file_path[-1]
            sep_ind = langfilename.rfind('.', 0, -5)
            if sep_ind != -1 and "labels" in json:
                yield from collect_langfiles(langfilename[:sep_ind],
                                             langfilename[sep_ind+1:-5],
                                             file_path, json["labels"])
            else:
                print("Found lang file without lang in filename:",
                      langfilename)
        else:
            yield from collect_langfiles(None, None, None, None)
            yield from add_file_path(file_path,
                                     walk_json_for_langlabels(json, orig_lang))

    yield from collect_langfiles(None, None, None, None)

def get_data_by_dict_path(json_obj, dict_path, include_reverse=False):
    """Traverse a json object by recursively indexing it along a path.

    'json_obj' must be a json object, i.e. a list or dict of list or dicts.
    'dict_path' is a list of str or int, which will be used as indexes.

    If 'include_reverse' is False, then return a subobject, or None if one of
    the index does not exist.
    If 'include_reverse' is True, then return subobject, reverse_path, where
    reverse_path are the subobject encountered during each index. reverse_path
    has the same length as dict_path and reverse_path[0] is json_obj.

    Note that this tolerate string index for arrays if the string is a decimal
    representation of an integer.

    >>> get_data_by_dict_path({"a": ["b", {"c": 5}]}, ["a", 1, "c"])
    5
    >>> get_data_by_dict_path({"a": ["b", {"c": 5}]}, ["a", "0"])
    'b'
    >>> get_data_by_dict_path({"a": ["b", {"c": 5}]}, ["a", "0"], True)
    'b', [{"a": ["b", {"c": 5}]}, ["b", {"c": 5}]]
    """
    reverse_path = []
    for component in dict_path:
        if include_reverse:
            reverse_path.append(json_obj)
        if isinstance(json_obj, list):
            try:
                json_obj = json_obj[int(component)]
            except:
                return None
        else:
            json_obj = json_obj.get(component)
            if json_obj is None:
                return None
    if include_reverse:
        return json_obj, reverse_path
    return json_obj


def serialize_dict_path(file_path, dict_path):
    """Return a string that represents both file_path and dict_path

    file_path and dict_path are assumed to be list of path components.
    """
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


def split_file_dict_path(file_dict_path_str):
    delimiter = '.json/'
    index = file_dict_path_str.index(delimiter)
    file_path = file_dict_path_str[:index + len(delimiter) - 1]
    dict_path = file_dict_path_str[index + len(delimiter):]
    return file_path, dict_path


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
    """Read specific translations given a path.

    This is faster than iterating over all files and filtering for this
    particular path.

    This also caches the last read file, to speed things even further."""
    def __init__(self, gamepath, default_lang):
        self.assets_path = get_assets_path(gamepath)
        self.data_path = os.path.join(self.assets_path, "data")
        self.last_loaded = None
        self.last_data = None
        self.default_lang = default_lang

    def load_file(self, file_path):
        if self.last_loaded == file_path:
            return None
        last_fail = None
        def try_load(usable_path):
            nonlocal last_fail
            try:
                self.last_data = load_json(usable_path)
                return True
            except Exception as ex:
                self.last_data = {}
                last_fail = ex
                return False
        file_path_str = os.sep.join(file_path)
        self.last_loaded = file_path
        if try_load(os.path.join(self.data_path, file_path_str)):
            return self.last_data

        if file_path[0] == "extension":
            if try_load(os.path.join(self.assets_path, file_path_str)):
                return self.last_data
        print("Cannot find game file:", file_path_str, ':', str(last_fail))
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

def filter_langlabel(lang_label, langs):
    for key in list(lang_label.keys()):
        if key not in langs:
            del lang_label[key]
    return lang_label

def trim_annotations(text):
    for endmark in ('<<C<<', '<<A<<'):
        index = text.find(endmark)
        if index != -1:
            return text[:index]
    return text

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
            filter_langlabel(entry["langlabel"], langs)
    def iterate_drain(self):
        for file_dict_path_str, entry in drain_dict(self.data):
            splitted_path = unserialize_dict_path(file_dict_path_str)
            yield entry["langlabel"], splitted_path, file_dict_path_str, entry
    def iterate(self):
        for file_dict_path_str, entry in self.data.items():
            splitted_path = unserialize_dict_path(file_dict_path_str)
            yield entry["langlabel"], splitted_path, file_dict_path_str, entry

    def add(self, file_dict_path_str, lang_label_like, extra=None):
        entry = {"langlabel": lang_label_like}
        if extra is not None:
            entry.update(extra)
        self.data[file_dict_path_str] = entry
    def delete(self, file_dict_path_str):
        del self.data[file_dict_path_str]
    def has(self, file_dict_path_str):
        return file_dict_path_str in self.data
    def size(self):
        return len(self.data)
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

def sort_pack_entry(entry):
    """Sort the entry of a pack so that fields are in this order:
    orig, text, quality, note, anythingelse(including partial)
    """

    order = {"orig":-4, "text":-3, "quality":-2, "note":-1}
    return dict(sorted(entry.items(), key=lambda kv: order.get(kv[0], 0)))

class PackFile:
    def __init__(self):
        self.reset()

    def reset(self):
        # dict from serialized file_dict_path to translation object
        # (e.g. {"orig": orig, "text": new})
        self.translations = {}
        # Index from orig to an object in self.translations
        self.translation_index = {}
        # Statistics about badnesses
        self.quality_stats = {"bad": 0, "incomplete": 0,
                              "unknown": 0, "wrong": 0, "spell": 0}

    def load(self, filename, on_each_text_load=lambda x: None):
        self.reset()

        self.translations = load_json(filename)
        for entry in self.translations.values():
            self.translation_index[entry['orig']] = entry
            self.add_quality_stat(entry)
            on_each_text_load(entry)

    def save(self, filename):
        try:
            os.rename(filename, filename+'~')
        except IOError:
            pass
        save_json(filename+".new", self.translations)
        os.rename(filename+".new", filename)

    def add_quality_stat(self, entry, shift=1):
        qual = entry.get("quality")
        if qual is not None:
            self.quality_stats[qual] += shift

    def add_incomplete_translation(self, dict_path_str, orig,
                                   incomplete_entry):
        assert 'text' not in incomplete_entry
        incomplete_entry["orig"] = orig
        incomplete_entry = sort_pack_entry(incomplete_entry)
        self.translations[dict_path_str] = incomplete_entry
        self.add_quality_stat(incomplete_entry)

    def add_translation(self, dict_path_str, orig, new_entry):
        new_entry["orig"] = orig
        new_entry = sort_pack_entry(new_entry)
        if dict_path_str in self.translations:
            self.add_quality_stat(self.translations[dict_path_str], -1)
        self.translations[dict_path_str] = new_entry
        self.add_quality_stat(new_entry)
        # this may erase duplicates, but may be more fitting to the context
        self.translation_index[orig] = new_entry

    def get_by_orig(self, orig):
        return self.translation_index.get(orig)

    def get(self, file_dict_path_str, orig_text=None):
        ret = self.translations.get(file_dict_path_str)
        if ret is None:
            return None
        if orig_text is not None and ret['orig'] != orig_text:
            return None
        return ret

    def get_all(self):
        return self.translations

    def get_stats(self, config):
        strings = len(self.translations)
        uniques = len(self.translation_index)

        def format_stat(count, out_of, label):
            if isinstance(out_of, int) and out_of > 1:
                return "%6i / %6i, %s (%.3f%%)" % (count, out_of, label,
                                                   100. * count / out_of)
            return "%6i %s" % (count, label)

        ret = format_stat(strings, config.total_count, "translations") + '\n'
        desc = {"unknown": "strings of unchecked quality",
                "bad": "badly formulated/translated strings",
                "incomplete": "strings with translated parts missing",
                "wrong": "translations that changes the meaning significantly",
                "spell": "translations with spelling errors"}
        for qual, count in self.quality_stats.items():
            ret += "%6i %s(%s)\n" % (count, desc[qual], qual)
        ret += format_stat(uniques, config.unique_count, "uniques")
        return ret

class GameWalker:
    """Walks the game files using either a directory to read from or a cache.

    Chooses semi-automatically which one to use, and supports filtering for
    files, dict_paths, tags or even a custom filter.
    """

    def __init__(self, game_dir=None, string_cache_path=None,
                 loaded_string_cache=None, from_locale="en_US"):
        self.string_cache = loaded_string_cache
        self.assets_dir = None
        self.file_path_filter = self.yes_filter
        self.dict_path_filter = self.yes_filter
        self.tags_filter = self.yes_filter
        self.orig_filter = self.yes_filter
        self.custom_filter = lambda path, langlabel: True
        self.from_locale = from_locale
        if loaded_string_cache is not None:
            return
        if string_cache_path and os.path.exists(string_cache_path):
            try:
                self.string_cache = string_cache(from_locale)
                self.string_cache.load_from_file(string_cache_path)
                return
            except:
                pass

        if game_dir is None:
            raise ValueError("No source configured or available")
        try:
            self.game_dir = game_dir
            self.assets_dir = get_assets_path(game_dir)
        except:
            raise RuntimeError("cannot find any game data source")

    def walk_cache(self, drain=True):
        if drain:
            iterator = self.string_cache.iterate_drain()
        else:
            iterator = self.string_cache.iterate()
        for langlabel, (file_path,
                        dict_path), file_dict_path_str, extra in iterator:
            if not self.file_path_filter(file_path):
                continue
            if not self.dict_path_filter(dict_path):
                continue

            info = self.custom_filter(file_dict_path_str, langlabel)
            if info is None:
                continue

            if not self.orig_filter((langlabel.get(self.from_locale, ""),)):
                continue

            tags = extra["tags"].split()
            if not self.tags_filter(tags):
                continue
            yield file_dict_path_str, langlabel, tags, info

    def walk_game_files(self, from_locale):
        iterable = walk_assets_for_translatables(self.assets_dir, from_locale,
                                                 self.file_path_filter)
        for langlabel, (file_path, dict_path), reverse_path in iterable:
            if not self.dict_path_filter(dict_path):
                continue

            file_dict_path_str = serialize_dict_path(file_path, dict_path)
            info = self.custom_filter(file_dict_path_str, langlabel)
            if info is None:
                continue

            if not self.orig_filter(langlabel.get(self.from_locale, "")):
                continue

            tags = tagger.find_tags(file_path, dict_path, reverse_path)
            if not self.tags_filter(tags):
                continue

            yield file_dict_path_str, langlabel, tags, info

    def walk(self, from_locale, drain=True):
        if self.string_cache is not None:
            return self.walk_cache(drain)
        return self.walk_game_files(from_locale)

    def walk_pack(self, pack):
        """Walk a pack file as if it was the game files.

        This assumes that the pack isn't too degenerated:
        - entries have an 'orig' field
        - they are not stale

        This yields file_dict_path_str and entries instead of yielding
        langlabel, (file_path, dict_path), reverse_path_or_info
        """

        sparse_reader = self.string_cache
        if sparse_reader is None:
            sparse_reader = sparse_dict_path_reader(self.game_dir,
                                                    self.from_locale)

        def filter_tags_and_custom_full(file_dict_path_str):
            complete = sparse_reader.get_complete_by_str(file_dict_path_str)
            if not complete:
                return None
            langlabel, (file_path, dict_path), rev_path_or_info = complete
            if self.tags_filter is not None:
                if isinstance(rev_path_or_info,
                              dict) and "tags" in rev_path_or_info:
                    tags = rev_path_or_info["tags"].split(" ")
                else:
                    tags = tagger.find_tags(file_path, dict_path,
                                            rev_path_or_info)
                if not self.tags_filter(tags):
                    return None
            if not self.custom_filter(file_dict_path_str, langlabel):
                return None

            return file_path, dict_path

        filter_tags_and_custom = filter_tags_and_custom_full

        if (self.tags_filter is self.yes_filter
                and self.custom_filter is self.yes_filter):
            filter_tags_and_custom = split_file_dict_path

        for file_dict_path_str, entry in pack.items():
            file_path_dict_path = filter_tags_and_custom(file_dict_path_str)
            if file_path_dict_path is None:
                continue
            file_path, dict_path = file_path_dict_path
            if not self.file_path_filter(file_path):
                continue
            if not self.dict_path_filter(dict_path):
                continue
            if not self.orig_filter((entry.get('orig',''),)):
                continue

            yield file_dict_path_str, entry

    def set_file_path_filter(self, array):
        self.file_path_filter = self.make_filter(array)

    def set_dict_path_filter(self, array):
        self.dict_path_filter = self.make_filter(array)

    def set_tags_filter(self, array):
        self.tags_filter = self.make_filter(array)

    def set_orig_filter(self, array):
        self.orig_filter = self.make_filter(array)

    def set_custom_filter(self, custom_filter):
        """set a custom filter.

        It will take a file_dict_path_str and a langlabel. If it returns None,
        the entry is filtered, else, the return value of this filter is yielded
        as the fourth entry of the tuple"""
        self.custom_filter = custom_filter

    @staticmethod
    def yes_filter(something):
        return True

    @classmethod
    def make_filter(cls, array):
        if not array:
            return cls.yes_filter
        if callable(array):
            return array
        array_of_ands = []
        for x in array:
            if isinstance(x, str):
                array_of_ands.append((x,))
            elif isinstance(x, list):
                array_of_ands.append(x)
            else:
                raise ValueError("bad value for filter: %s"%repr(x))
        def check_filter(some_path_as_list):
            for candidate in array_of_ands:
                if all(c in some_path_as_list for c in candidate):
                    return True
            return False
        return check_filter

def transform_file_or_dir(input_path, output_path):
    """Browse all files in input_file and transform them into output_path.

    e.g. you can reimplement cp -r with:
    for a,b,c in transform_file_or_dir(arg1, arg2):
        open(b, "w").write(open(a).read())

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
