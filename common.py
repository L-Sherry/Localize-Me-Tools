#!/bin/echo This file is not meant to be executable:

import os, os.path, json

load_json = lambda p: json.load(open(p, encoding="utf-8"))
save_json_to_fd = lambda fd, v: json.dump(v, fd, indent=8,
                                          separators=(',',': '),
                                          ensure_ascii=False)

save_json = lambda p, v: save_json_to_fd(open(p, 'w', encoding="utf-8"), v)

def walk_json_inner(json, dict_path = None, reverse_path = None):
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
        iterable = ((str(i), value) for i,value in enumerate(json))
    else:
        return
    for k,v in iterable:
        dict_path.append(k)
        reverse_path.append(json)
        yield from walk_json_inner(v, dict_path, reverse_path)
        popped_k = dict_path.pop()
        popped_json = reverse_path.pop()
        assert popped_k is k and popped_json is json

def walk_json_for_langlabels(json, lang_to_check):
    iterator = walk_json_inner(json)
    for value, dict_path, reverse_path in iterator:
        if isinstance(value, dict) and lang_to_check in value:
            iterator.send(False)
            yield value, dict_path, reverse_path

def walk_langfile_json(json, lang):
    for value, dict_path, reverse_path in walk_json_inner(json):
        if len(dict_path) == 1:
            continue
        elif not isinstance(value, str):
            continue
        yield { lang: value }, dict_path, reverse_path

def walk_files(base_path, sort = True):
    for dirpath, subdirs, filenames in os.walk(base_path, topdown=True):
        subdirs.sort()
        for name in sorted(filenames) if sort else filenames:
            usable_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(usable_path, base_path)
            yield usable_path, rel_path

def walk_assets_for_translatables(path, orig_lang,
                                  path_filter = lambda x: True):
    base_path = os.path.join(get_assets_path(path), "data")

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

def get_data_by_dict_path(json, dict_path):
    for component in dict_path:
        if isinstance(json, list):
            try:
                json = json[int(component)]
            except:
                return None
        else:
            json = json.get(component)
            if json is None:
                return None
    return json


def serialize_dict_path(file_path, dict_path):
    # FIXME: we need a better encoding maybe.
    # eg: escape / in keys with \, escape \ with \ as well, and find
    # a way to handle json files not having a .json extension.
    assert file_path[-1][-5:] == ".json"
    return "%s/%s"%("/".join(file_path), "/".join(dict_path))

def unserialize_dict_path(dict_path_str):
    l = dict_path_str.split('/')
    for index, value in enumerate(l):
        if value.endswith('.json'):
            return (l[:index+1], l[index+1:])
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
        else:
            raise ValueError("could not find game assets." 
                             " Searched in %s and %s/assets"%(path, path))
    else:
        return path + ("%s.."%os.sep) * (len(realsplit) - index - 1)

class sparse_dict_path_reader:
    def __init__(self, gamepath, lang):
        self.base_path = os.path.join(get_assets_path(gamepath), "data")
        self.last_loaded = None
        self.last_data = None
        self.lang = lang

    def get(self, file_path, dict_path):
        if self.last_loaded != file_path:
            usable_path = os.path.join(self.base_path, os.sep.join(file_path))
            try:
                self.last_data = load_json(usable_path)
            except Exception as e:
                print("Cannot find game file:", "/".join(file_path), ':',
                      str(e))
                self.last_data = {}
            self.last_loaded = file_path

        ret = get_data_by_dict_path(self.last_data, dict_path)
        if file_path[0] != "lang" and ret is not None:
            assert isinstance(ret, dict)
            return ret.get(self.lang)
        return ret

    def get_str(self, file_dict_path_str):
        file_path, dict_path = unserialize_dict_path(file_dict_path_str)
        return self.get(file_path, dict_path)



def transform_file_or_dir(input_path, output_path):
    """Browse all files in input_file and transform them into output_path.

    e.g. you can reimplement cp -r with:
    for a,b in transform_file_or_dir(arg1, arg2):
        open(a, "w").write(open(b).read()

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
