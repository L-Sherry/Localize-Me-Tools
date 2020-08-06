#!/usr/bin/python3

import base64
import hmac
import hashlib
import os
import sys

try:
    # The only thing not part of python
    import Crypto.Cipher.AES
except Exception:
    print("pycrypto not found. crypto operations will fail !")

import common


class Encraption:
    """Encrapt stuff to protect against lawyers

    Encrapt stuff so that lawyers cannot tell us we're distributing copyrighted
    stuff in the 'orig' and derived works in 'text' to people that don't
    have the original material.

    Any lawless thug can workaround this encraption, that's not the problem.

    List of things that we do that would horify a crypto researcher:
    - md5 of low entropy text as key derivation
    - key == iv
    - mac key = aes key
    - vulnerable reimplementation of pkcs7
    - encrypt and mac
    """
    def __init__(self, orig_text):
        self.key = hashlib.md5(orig_text.encode('utf-8')).digest()

    # no pkcs7 in pycrypto ?
    @staticmethod
    def _pkcs7pad(pad_length):
        return bytes(pad_length for x in range(pad_length))

    def _aes(self):
        return Crypto.Cipher.AES.new(self.key, Crypto.Cipher.AES.MODE_CBC,
                                     self.key)

    def encrapt_text(self, text):
        text = text.encode("utf-8")
        pad_length = 16 - len(text) % 16
        padded_text = text + self._pkcs7pad(pad_length)
        ciphertext = self._aes().encrypt(padded_text)
        return base64.b64encode(ciphertext).decode('ascii')

    def decrapt_text(self, ciphertext):
        ciphertext = base64.b64decode(ciphertext.encode('ascii'))
        # hey, i only need to defend against lawyers.
        padded_text = self._aes().decrypt(ciphertext)
        pad_length = padded_text[-1]
        if not (0 < pad_length <= 16
                and padded_text[-pad_length:] == self._pkcs7pad(pad_length)):
            print("ciphertext:", repr(ciphertext))
            print("decrapt:", repr(padded_text), "with key", repr(self.key))
            print("FAIIIIIIIIIIIIIIIIL")
            raise ValueError("bad pcks7 padding")
        # print("decrapt[:-pad]:", repr(padded_text[:-pad_length]))
        return padded_text[:-pad_length].decode('utf-8')

    def mac_text(self, text):
        # didn't find anything else but md5 in the loaded JS.
        mac = hmac.digest(self.key, text.encode('utf-8'), 'md5')
        return base64.b64encode(mac).decode('ascii')

    @staticmethod
    def encrapt_trans(trans_object):

        enc = Encraption(trans_object['orig'])
        text = trans_object['text']

        ret = {"ciphertext": enc.encrapt_text(text), "mac": enc.mac_text(text)}

        quality = trans_object.get('quality')
        if quality is not None:
            ret["quality"] = quality
        if "reason" in trans_object:
            # was equivalent to 'note'
            raise ValueError("Throw out this old file, bro")
        note = trans_object.get('note')
        if note:
            ret["ciphernote"] = enc.encrapt_text(note)
        return ret

    @staticmethod
    def decrapt_trans(trans_object, orig):
        if "text" in trans_object:
            raise ValueError("It's not encrypted ?")
        enc = Encraption(orig)
        text = enc.decrapt_text(trans_object["ciphertext"])
        mac = trans_object.get("mac")
        if mac is not None and mac != enc.mac_text(text):
            raise ValueError("MAC mismatch")
        ret = {'orig': orig, 'text': text}
        quality = trans_object.get("quality")
        if quality is not None:
            ret["quality"] = quality
        ciphernote = trans_object.get("ciphernote")
        if ciphernote is not None:
            ret["note"] = enc.decrapt_text(ciphernote)
        return ret


def sort_by_game(game_walker, from_locale, pack):
    def get_file_path_tuple(file_dict_path_str):
        return tuple(common.unserialize_dict_path(file_dict_path_str)[0])

    # file_path_tuple => pack for that file path
    packs_by_file = {}
    for file_dict_path_str, result in pack.items():
        file_path_tuple = get_file_path_tuple(file_dict_path_str)
        pack = packs_by_file.setdefault(file_path_tuple, {})
        pack[file_dict_path_str] = result

    known_files = frozenset(packs_by_file.keys())
    game_walker.set_file_path_filter(lambda f_p: tuple(f_p) in known_files)

    current_file = None
    strings_for_file = None

    output = {}

    def add_stale_for_current_file():
        if strings_for_file:
            print("note: sorting", len(strings_for_file),
                  "stale nonexisting strings for", "/".join(current_file))
            output.update(common.sort_dict(strings_for_file))
            strings_for_file.clear()

    iterator = game_walker.walk(from_locale, False)

    for file_dict_path_str, _, _, _ in iterator:
        file_path = get_file_path_tuple(file_dict_path_str)
        if current_file != file_path:
            add_stale_for_current_file()
            current_file = file_path
            strings_for_file = packs_by_file.pop(file_path, {})

        result = strings_for_file.pop(file_dict_path_str, None)
        if result is not None:
            output[file_dict_path_str] = result

    # sort remains of the last file
    add_stale_for_current_file()

    # sort the remaining stales file_path, and add them
    for file_path, pack in common.sort_dict(packs_by_file):
        print("note: sorting", len(pack), "strings for nonexisting",
              "/".join(file_path))
        output.update(common.sort_dict(pack))

    return output


def get_walker(args):
    return common.GameWalker(game_dir=args.gamedir,
                             string_cache_path=args.string_cache,
                             from_locale=args.from_locale)


def get_sorter(args):
    if args.sort_order == "none":
        return lambda pack: pack
    elif args.sort_order == "alpha":
        return common.sort_dict
    elif args.sort_order == "game":
        walker = get_walker(args)
        from_locale = args.from_locale
        return lambda pack: sort_by_game(walker, from_locale, pack)
    else:
        raise ValueError("Invalid sort order %s (allowed: none, alpha, game)"
                         % repr(args.sort_order))


def get_sparse_reader(args):
    # TODO: this duplicates code in jsontr.py, should move this into GameWalker
    if os.path.exists(args.string_cache):
        string_cache = common.string_cache(args.from_locale)
        string_cache.load_from_file(args.string_cache)
        return string_cache
    return common.sparse_dict_path_reader(args.gamedir,
                                          args.from_locale)


def do_encrapt(args):
    sorter = get_sorter(args)

    try:
        sparse_reader = get_sparse_reader(args)
    except Exception as e:
        sparse_reader = None
        print("Cannot find game assets:", str(e),
              " continuing by trusting the packfiles")

    error = False
    iterator = common.transform_file_or_dir(args.inputpath, args.outputpath)
    for input_file, output_file, rel_path in iterator:
        json = common.load_json(input_file)
        result = {}
        for file_dict_path_str, value in json.items():
            orig_in_file = value.get('orig')
            orig_in_game = None
            if sparse_reader is not None:
                orig_in_game = sparse_reader.get_str(file_dict_path_str)
                if orig_in_file is None:
                    value['orig'] = orig_in_game
                elif orig_in_game is not None and orig_in_game != orig_in_file:
                    orig_in_game = None
                if orig_in_game is None:
                    print("Not encrapting stale translation at",
                          file_dict_path_str)
                    print("true orig:", orig_in_game)
                    print(" our orig:", orig_in_file)
                    error = True
                    continue
            result[file_dict_path_str] = Encraption.encrapt_trans(value)
        common.save_json(output_file, sorter(result))
    if error:
        sys.exit(1)


def do_decrapt(args):
    sorter = get_sorter(args)
    sparse_reader = get_sparse_reader(args)
    iterator = common.transform_file_or_dir(args.inputpath, args.outputpath)
    error = False
    for input_file, output_file, _ in iterator:
        try:
            json = common.load_json(input_file)
        except Exception as e:
            print("Cannot read", input_file, ":", str(e))
            continue
        result = {}
        for file_dict_path_str, value in json.items():
            # print("filedictpath", repr(file_dict_path_str))
            orig = sparse_reader.get_str(file_dict_path_str)
            if orig is None:
                print("Cannot read original translation at",
                      file_dict_path_str)
                error = True
                continue
            try:
                decrapted = Encraption.decrapt_trans(value, orig)
            except Exception as e:
                print("Cannot decrypt (is translation stale?):", str(e),
                      "at", file_dict_path_str)
                error = True
                continue
            result[file_dict_path_str] = decrapted
        common.save_json(output_file, sorter(result))
    if error:
        sys.exit(1)


def do_make_mapfile(args):
    json = common.load_json(args.bigpack)
    result = {}
    prefix = args.prefix
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    for file_dict_path_str in json.keys():
        file_path, _ = common.unserialize_dict_path(file_dict_path_str)
        path = "/".join(file_path)
        result[path] = prefix + path
    common.save_json(args.mapfile, result)


def do_split(args):
    sorter = get_sorter(args)

    big_pack = common.load_json(args.bigpack)
    map_file = common.load_json(args.mapfile)
    results = {}
    error = False
    for file_dict_path_str, trans in big_pack.items():
        file_path, _ = common.unserialize_dict_path(file_dict_path_str)
        file_path_str = "/".join(file_path)
        to_file_str = map_file.get(file_path_str)
        if to_file_str is None:
            print("missing pack reference for", file_path_str)
            error = True

        results.setdefault(to_file_str, {})[file_dict_path_str] = trans

    if error:
        print("Aborting...")
        sys.exit(1)

    for to_file_str, smaller_pack in results.items():
        to_file = to_file_str.split('/')[args.strip:]
        if not to_file:
            print("strip parameter", args.strip, "is too large for path",
                  to_file_str)
            print("Aborting...")
            sys.exit(1)

        actual_dir = os.path.join(args.outputpath, os.sep.join(to_file[:-1]))
        os.makedirs(actual_dir, exist_ok=True)
        smaller_pack = sorter(smaller_pack)
        common.save_json(os.path.join(actual_dir, to_file[-1]), smaller_pack)


def do_merge(args):
    sorter = get_sorter(args)

    big_result = {}
    error = False
    for usable_path, _ in common.walk_files(args.inputpath):
        for file_dict_path_str, value in common.load_json(usable_path).items():
            if big_result.setdefault(file_dict_path_str, value) != value:
                print("Multiple different value found for", file_dict_path_str)
                error = True
    if error:
        if args.allow_mismatch:
            print("Continuing anyway...")
        else:
            print("Aborting...")
            sys.exit(1)
    big_result = sorter(big_result)

    common.save_json(args.bigpack, big_result)


def do_diff_langfile(args):
    from_json = common.load_json(args.fileorig)
    to_json = common.load_json(args.filetrans)
    if "filename" in args and args.filename is not None:
        file_path = args.filename.split('/')
    else:
        file_path = ["lang", "sc", os.path.basename(args.fileorig)]
    result = {}
    iterator = common.walk_langfile_json(from_json, "orig")
    for trans, dict_path, _ in iterator:
        text = common.get_data_by_dict_path(to_json, dict_path)
        if text is None:
            continue
        trans['text'] = text
        result[common.serialize_dict_path(file_path, dict_path)] = trans
    # we are already sorted by game order
    if args.sort_order == "alpha":
        result = common.sort_dict(result)
    if args.resultfile == '-':
        common.save_json_to_fd(sys.stdout, result)
    else:
        common.save_json(args.resultfile, result)


class SparsePriorityQueue:
    """A container that store values ordered by a score

    It is assumed that values are way sparser than scores, i.e. they are
    way less possible scores than there are values."""
    def __init__(self):
        # score => [values], that's it.
        self.prio_to_value = {}

    def insert(self, score, value):
        """Insert a value with the given score"""
        self.prio_to_value.setdefault(score, []).append(value)

    def __iter__(self):
        """Iterate on values only"""
        for key in sorted(self.prio_to_value.keys()):
            yield from self.prio_to_value[key]


class MigrationCalculator:
    """Matches a source string cache to a destination string and migrate packs

    Uses a nondeterministic polynomial complete algorithm"""
    def __init__(self, source_string_cache, destination_string_cache):
        self.src = source_string_cache
        self.dest = destination_string_cache
        # Maps old file_dict_path to new file_dict_path (or None if unchanged)
        self.map = {}

    # the code below assumes same file matches trump all other matches
    SAME_FILE = 1000
    SAME_DICT_PATH = 100
    SAME_FIELD = 100
    # Arbitrary score when everything matches.
    MAX_SCORE = 10000
    # Arbitrary score when a langfile was moved as-is in the same file.
    SAME_FILE_MAX_SCORE = 5000

    @classmethod
    def match_score(cls, src_file_dict_path, dest_file_dict_path,
                    src_langlabel, dest_langlabel):
        """If it returns 0, then match should be forbidden"""
        base_score = 0
        if src_file_dict_path == dest_file_dict_path:
            base_score = cls.SAME_FILE + cls.SAME_DICT_PATH
        else:
            src_file, src_path = common.split_file_dict_path(src_file_dict_path)
            dest_file_path = common.split_file_dict_path(dest_file_dict_path)
            dest_file, dest_path = dest_file_path
            if src_file == dest_file:
                base_score = cls.SAME_FILE
            elif src_path == dest_path:
                base_score += cls.SAME_DICT_PATH

        field_perfect = True
        field_score = 0
        for key, value in src_langlabel.items():
            if value == "" or value == key:
                continue
            if dest_langlabel.get(key) == value:
                field_score += cls.SAME_FIELD
            else:
                field_perfect = False

        if base_score == cls.SAME_FILE + cls.SAME_DICT_PATH and field_perfect:
            return cls.MAX_SCORE
        if base_score == cls.SAME_FILE and field_perfect:
            return cls.SAME_FILE_MAX_SCORE
        return base_score + field_score

    def assign(self, src_file_dict_path, dest_file_dict_path, is_exact):
        """Assign the given source to the given dest and drain them

        Draining is used to reduce the pressure on the following algorithms"""
        if is_exact and src_file_dict_path == dest_file_dict_path:
            self.map[src_file_dict_path] = None
        else:
            self.map[src_file_dict_path] = dest_file_dict_path
        self.src.delete(src_file_dict_path)
        self.dest.delete(dest_file_dict_path)

    def do_greddy_map(self):
        """Drain both string caches with perfect matches

        Return number of drained elements"""
        perfect_matches = []
        # still can't drain while iterating ?
        for src_langlabel, _, src_file_dict_path, _ in self.src.iterate():
            dest_ll = self.dest.get_complete_by_str(src_file_dict_path)[0]
            if dest_ll is None:
                continue
            if self.match_score(src_file_dict_path, src_file_dict_path,
                                src_langlabel, dest_ll) == self.MAX_SCORE:
                perfect_matches.append(src_file_dict_path)

        for match in perfect_matches:
            self.assign(match, match, True)
        return len(perfect_matches)

    def assignment_algorithm(self, src_map, dest_map, prio_queue,
                             perfect_score=None, minimum_score=0):
        """Attempt to find an assignment from src_map to dest_map

        src_map must be a subset of self.src and dest_map must be a subset
        of self.dest.  prio_queue must be a SparsePriorityQueue.
        If perfect_score is set and reached, then assume this is the best
        possible outcome and assign it on the spot, to stop trying to search
        for anything better.

        After this runs, prio_queue will contain a priority queue with the
        best scores sorted first.  The prio_queue's values will be
        (src_file_dict_path, dest_file_dict_path)

        Return the number of assignment done because of perfect_score
        """
        if perfect_score is None:
            perfect_score = 2**30
        perfect_matches = 0
        for src_file_dict_path, src_langlabel in src_map.items():
            potential_mappings = []
            for dest_file_dict_path, dest_langlabel in dest_map.items():
                score = self.match_score(src_file_dict_path,
                                         dest_file_dict_path,
                                         src_langlabel, dest_langlabel)
                if score >= perfect_score:
                    self.assign(src_file_dict_path, dest_file_dict_path, True)
                    perfect_matches += 1
                    del dest_map[dest_file_dict_path]
                    break
                if score <= minimum_score:
                    continue
                potential_mappings.append((-score,
                                           (src_file_dict_path,
                                            dest_file_dict_path)))
            else:
                for score, mapping in potential_mappings:
                    prio_queue.insert(score, mapping)
        return perfect_matches

    def assign_by_prio_queue(self, prio_queue):
        for src_file_dict_path, dest_file_dict_path in prio_queue:
            if not self.src.has(src_file_dict_path):
                continue
            if not self.dest.has(dest_file_dict_path):
                continue
            self.assign(src_file_dict_path, dest_file_dict_path, False)

    @staticmethod
    def sort_by_file(string_cache):
        by_file = {}
        for langlabel, _, file_dict_path_str, _ in string_cache.iterate():
            file_str = common.split_file_dict_path(file_dict_path_str)[0]
            map_for_file = by_file.setdefault(file_str, {})
            map_for_file[file_dict_path_str] = langlabel
        return by_file
    def do_same_file_map(self):
        """Assign lang files that moved within the same file

        Return number of drained elements, number of perfect matches"""

        orig_size = self.src.size()
        src_by_file = self.sort_by_file(self.src)
        dest_by_file = self.sort_by_file(self.dest)
        perfect_matches = 0

        for src_file_str, src_per_file_map in src_by_file.items():
            dest_per_file_map = dest_by_file.get(src_file_str)
            if dest_per_file_map is None:
                continue

            prio_queue = SparsePriorityQueue()

            perfects = self.assignment_algorithm(src_per_file_map,
                                                 dest_per_file_map,
                                                 prio_queue,
                                                 self.SAME_FILE_MAX_SCORE)
            perfect_matches += perfects
            self.assign_by_prio_queue(prio_queue)

        return orig_size - self.src.size(), perfect_matches

    def do_remaining(self):
        """Perform an assignment from everything to everything

        This is slow, use it after everything else.
        Return number of drained elements
        """
        def all_of_them(string_cache):
            ret = {}
            for langlabel, _, file_dict_path_str, _ in string_cache.iterate():
                ret[file_dict_path_str] = langlabel
            return ret
        big_prio_queue = SparsePriorityQueue()
        src_map = all_of_them(self.src)
        dest_map = all_of_them(self.dest)
        self.assignment_algorithm(src_map, dest_map, big_prio_queue)
        self.assign_by_prio_queue(big_prio_queue)
        return len(src_map) - self.src.size()

    def do_everything(self, no_interfile_move=False):
        perfect = self.do_greddy_map()
        same_file, perfect_same_file = self.do_same_file_map()
        remaining = 0
        if not no_interfile_move:
            remaining = self.do_remaining()

        print("Migration statistics:")
        print("Unchanged                   : %7d" % perfect)
        print("Moved as-is in same file    : %7d" % perfect_same_file)
        print("Found modified in same file : %7d" % same_file)
        print("Matched in another file     : %7d" % remaining)
        print("")
        print("Unmigrated lang labels (to delete) : %7d" % self.src.size())
        print("New lang labels                    : %7d" % self.dest.size())
    def write_json(self, path):
        unchanged = []
        delete = []
        migrate = {}
        for from_str, to_str in self.map.items():
            if to_str is None:
                unchanged.append(from_str)
            else:
                migrate[from_str] = to_str
        for _, _, file_dict_path_str, _ in self.src.iterate():
            delete.append(file_dict_path_str)

        unchanged.sort()
        delete.sort()
        migrate = common.sort_dict(migrate)

        json = {"migrate": migrate, "delete": delete, "unchanged": unchanged}
        common.save_json(path, json)


def do_calcmigrate(args):
    source = common.string_cache()
    dest = common.string_cache()
    source.load_from_file(args.source_string_cache)
    dest.load_from_file(args.dest_string_cache)
    migrator = MigrationCalculator(source, dest)
    migrator.do_everything(bool(args.no_file_move))
    migrator.write_json(args.migration_plan)


def do_migrate(args):
    sorter = get_sorter(args)
    sparse_reader = get_sparse_reader(args)
    plan = common.load_json(args.migration_plan)
    to_delete = set(plan["delete"])
    unchanged = set(plan["unchanged"])
    migrate = plan["migrate"]
    iterator = common.transform_file_or_dir(args.inputpath, args.outputpath)
    for input_file, output_file, _ in iterator:
        try:
            src_pack = common.load_json(input_file)
        except Exception as e:
            print("Cannot read", input_file, ":", str(e))
            continue

        result = {}
        for file_dict_path_str, value in src_pack.items():
            if file_dict_path_str in unchanged:
                result[file_dict_path_str] = value
                continue
            if file_dict_path_str in to_delete:
                continue
            new_file_dict_path_str = migrate.get(file_dict_path_str)
            if new_file_dict_path_str is None:
                print("No match for %s" % file_dict_path_str)
                continue

            value['orig'] = sparse_reader.get_str(new_file_dict_path_str)
            result[new_file_dict_path_str] = value

        common.save_json(output_file, sorter(result))


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Command to manage pack"
                                                 " files\n")
    parser.add_argument('--game-dir', '-g', metavar="directory",
                        default='.', dest="gamedir",
                        help="""Location of the installed game's assets/
                        directory. Any subdirectory of it is also accepted.
                        Search around the current directory by default.""")
    parser.add_argument('--from-locale', '-l', metavar="locale",
                        default="en_US", dest="from_locale",
                        help="""Locale used for origin, defaults to en_US.""")
    parser.add_argument('--map-file', '-m', metavar="file", dest="mapfile",
                        default="map_file.json",
                        help="""Location of the file containing the mapping
                        from original game files to location of pack file
                        with the translated texts""")
    parser.add_argument('--string-cache', metavar="file", dest="string_cache",
                        default="string_cache.json",
                        help="""Location of the string cache, used to speed up
                        string lookups. If not present, the installed game will
                        be used instead""")
    parser.add_argument('--sort-output', metavar="order", dest="sort_order",
                        default="none",
                        help="""For commands that write packs, indicate how
                        the pack should be sorted. "none" means to preserve the
                        original order, "alpha" mean to sort the file_dict_path
                        by alphanumerical sort (by unicode code point),
                        "game" mean to sort by the order in which they appear
                        in the game file(s) (slow).""")

    def add_stuffpath(stuff, parser, **kw):
        kw.setdefault("metavar", "<%s dir or file>" % stuff)
        parser.add_argument("%spath" % stuff, **kw)

    def add_inputpath(parser, **kw):
        add_stuffpath("input", parser, **kw)

    def add_outputpath(parser, **kw):
        add_stuffpath("output", parser, **kw)

    def add_bigpack(parser, halp):
        parser.add_argument("bigpack", metavar="<big pack>", help=halp)

    subparsers = parser.add_subparsers(metavar="COMMAND", required=True)
    encrapt = subparsers.add_parser(
        'encrapt', help="encrypt one or multiple packfiles",
        description="""read one or multiple pack files and write the
                       encrapted output.  If the input is a directory, the
                       output must be a directory.""")
    add_inputpath(encrapt, help="""unencrypted pack file or directory
                                   containing pack files""")
    add_outputpath(encrapt, help="""where to write encrapted pack file(s)""")
    encrapt.set_defaults(func=do_encrapt)

    decrapt = subparsers.add_parser(
        'decrapt', help="decrypt one or multiple packfiles",
        description="""read one or multiple pack files and write the
                       decrapted output.  This command requires --gamedir
                       and --from-locale to be set correctly.  If the input
                       is a directory, the output must be a directory.""")
    add_inputpath(decrapt, help="""encrapted pack file or directory containing
                                   pack files""")
    add_outputpath(decrapt, help="""where to write decrapted pack file(s)""")
    decrapt.set_defaults(func=do_decrapt)

    make_map = subparsers.add_parser(
        'mkmap', help="create a default map file for 'split'",
        description="""Read a big packfile and write a map file
                       with sensible default values.  The map file can then
                       be customized manually afterward, or can be used
                       with split as-is.""")
    add_bigpack(make_map, "pack file to use as a template to create the map")
    make_map.add_argument("--prefix", default="", help="""prefix to use before
                          packs.  e.g. if specifing mods/mymod/packs, then all
                          small pack will be stored as a subdirectory of
                          mods/mymod/packs/""")
    make_map.set_defaults(func=do_make_mapfile)

    split = subparsers.add_parser(
        'split', help="split a big packfile into small ones",
        description="""Read a big packfile and a map file and
                       write several smaller packfile, controlled by the
                       map file""")

    add_bigpack(split, "pack file to split")
    add_stuffpath("output", split, metavar="<output dir>",
                  help="""where to write the smaller packs, according to the
                          map file""")
    split.add_argument("--strip", "-p", type=int, default=0,
                       help="""strip this amount of directories before writing
                       to the output. e.g. if the map file references
                       mods/mymod/packs/a, then --strip=2 will write it as
                       packs/a in the output directory.""")
    split.set_defaults(func=do_split)

    merge = subparsers.add_parser(
        'merge', help="merge several packfiles into a big one",
        description="""Merge all packfiles in a directory into a
                       bigger one.""")
    add_inputpath(merge, metavar="<input dir>",
                  help="""Where to search for packfiles""")
    add_bigpack(merge, """Where to write the big packfile""")
    merge.add_argument("--allow-mismatch", dest="allow_mismatch",
                       action="store_true", help="""If two input pack files
                       possess different translation for the same string, then
                       warn and pick the first encountered one.  The default is
                       to abort in this case.""")
    merge.set_defaults(func=do_merge)

    difflang = subparsers.add_parser(
        'difflang', help="Calculate differences between two lang files",
        description="""Given two lang files, calculate the difference as
                       a pack file and write the output.  Lang files are
                       files that typically resides under the lang/
                       directory.""")
    difflang.add_argument("--file-path",
                          dest="filename", metavar="<path of original name",
                          help="""Path to use to refer to the difference in the
                          output. The default is to use 'lang/sc/<filename>'
                          where filename is the name of <original file>""")
    difflang.add_argument("fileorig", metavar="<original file>",
                          help="""Original file to use as starting point""")
    difflang.add_argument("filetrans", metavar="<translated file>",
                          help="""Translated original file""")
    difflang.add_argument("resultfile", metavar="<output file>",
                          help="""Where to write the output.  If '-', then
                                  output to the standard output""")
    difflang.set_defaults(func=do_diff_langfile)


    calcmigrate = subparsers.add_parser(
        'calcmigration', help="Migrate pack files from a version to another",
        description="""Given a source string cache and a destination string
                       cache, match source lang labels to destination lang
                       labels using a matching algorithm and write a migration
                       plan to apply later with 'migrate'.  This can be used
                       to updrade packs to the latest version of the game.""")
    calcmigrate.add_argument("source_string_cache",
                             metavar="<source string cache>",
                             help="""string cache containing lang labels to
                                     migrate from""")
    calcmigrate.add_argument("dest_string_cache", metavar="<dest string cache>",
                             help="""string cache containing lang labels to
                                     migrate to""")

    calcmigrate.add_argument("migration_plan", metavar="<migration plan>",
                             help="""Where to write the migration plan in JSON
                                     format""")
    calcmigrate.add_argument("--no-file-move", dest="no_file_move",
                             action="store_true",
                             help="""Do not match old lang labels into lang
                                     labels in a different (game) file.""")
    calcmigrate.set_defaults(func=do_calcmigrate)

    migrate = subparsers.add_parser(
        'migrate', help="""Given a pack file or directory and a migration plan,
                           migrate it and write a new pack file or directory""")
    migrate.add_argument("migration_plan", metavar="<migration plan file>",
                         help="""Migration plan JSON file as calculated by
                                 'calcmigration'""")
    add_inputpath(migrate, help="""pack file or directory to migrate from""")
    add_outputpath(migrate, help="""Where to write migrated pack file(s)""")
    migrate.set_defaults(func=do_migrate)


    result = parser.parse_args()
    result.func(result)


if __name__ == "__main__":
    parse_args()
