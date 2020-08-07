#!/usr/bin/python3

"""Set of utilities to manipulate pack files.  Run --help for details."""

import os
import sys
import types
import common


def sort_by_game(game_walker, from_locale, pack):
    """Sort a pack by the order in which strings appears in the game files.

    This is one of the slowest sorting method.  If the pack contains strings
    that are not present in the game, they are sorted alphabetically at the
    end and a message is logged."""

    def get_file_path_tuple(file_dict_path_str):
        return tuple(common.unserialize_dict_path(file_dict_path_str)[0])

    def get_packs_by_file(pack):
        """Return a dict from file_path_tuple to a pack for that file path"""
        packs_by_file = {}
        for file_dict_path_str, result in pack.items():
            file_path_tuple = get_file_path_tuple(file_dict_path_str)
            pack = packs_by_file.setdefault(file_path_tuple, {})
            pack[file_dict_path_str] = result
        return packs_by_file

    packs_by_file = get_packs_by_file(pack)

    known_files = frozenset(packs_by_file.keys())
    game_walker.set_file_path_filter(lambda f_p: tuple(f_p) in known_files)

    def iterate_game_and_pick_translations(packs_by_file, game_walker):
        """Iterate with game_walker and drain packs_by_file

        Return a sorted single pack with elements in the same order as
        returned by game_walker with translations from packs_by_file.

        This will drain packs_by_file in the process, so only stale strings
        will remain there."""

        output = {}
        iterator = game_walker.walk(from_locale, False)

        current_file = None
        strings_for_file = None

        def add_stale_for_current_file():
            """Add strings remaining in strings_for_file to stale translations

            Called after iterating for all strings in one game file."""
            if strings_for_file:
                print("note: sorting", len(strings_for_file),
                      "stale nonexisting strings for", "/".join(current_file))
                output.update(common.sort_dict(strings_for_file))
                strings_for_file.clear()

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
        return output

    output = iterate_game_and_pick_translations(packs_by_file, game_walker)

    # sort the remaining stales file_path, and add them
    for file_path, stale_pack in common.sort_dict(packs_by_file):
        print("note: sorting", len(stale_pack), "strings for nonexisting",
              "/".join(file_path))
        output.update(common.sort_dict(stale_pack))

    return output


def get_walker(args):
    """Return a correctly configured GameWalker given argparse parameters"""
    return common.GameWalker(game_dir=args.gamedir,
                             string_cache_path=args.string_cache,
                             from_locale=args.from_locale)


def get_sorter(args):
    """Return a pack sorting function according to the argparse parameters.

    This sort function takes one pack as parameter and returns another.
    The parameter may be modified and should not be used afterward.
    """
    if args.sort_order == "none":
        return lambda pack: pack
    if args.sort_order == "alpha":
        return common.sort_dict
    if args.sort_order == "game":
        walker = get_walker(args)
        from_locale = args.from_locale
        return lambda pack: sort_by_game(walker, from_locale, pack)

    raise ValueError("Invalid sort order %s (allowed: none, alpha, game)"
                     % repr(args.sort_order))


def get_sparse_reader(args):
    """Return a configured sparse reader given argparse parameters.

    This will pick the one with the highest performance.  It will prefer
    string caches to browsing every game file."""
    # TODO: this duplicates code in jsontr.py, should move this into GameWalker
    if os.path.exists(args.string_cache):
        string_cache = common.string_cache(args.from_locale)
        string_cache.load_from_file(args.string_cache)
        return string_cache
    return common.sparse_dict_path_reader(args.gamedir,
                                          args.from_locale)


def do_make_mapfile(args):
    """Create a default mapfile with a one file to one file mapping."""
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
    """Split a large packfile to multiple ones according to a mapfile"""
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
    """Merge multiple pack files into one big pack file."""
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
    """Calculate a pack file given two lang files."""
    from_json = common.load_json(args.fileorig)
    to_json = common.load_json(args.filetrans)
    if "filename" in args and args.filename is not None:
        file_path = args.filename.split('/')
    else:
        file_path = ["lang", "sc", os.path.basename(args.fileorig)]
    result = {}
    # This is arbitrary. "foobar" or "en_US" would also work.
    from_locale = args.from_locale
    iterator = common.walk_langfile_json({from_locale: from_json}, [], [])
    for langlabel, dict_path, _ in iterator:
        text = common.get_data_by_dict_path(to_json, dict_path)
        if text is None:
            continue
        trans = {"orig": langlabel[from_locale], "text": text}

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
    def base_match_score(cls, src_file_dict_path, dest_file_dict_path):
        """Calculate the base match score from file dict paths alone."""
        if src_file_dict_path == dest_file_dict_path:
            return cls.SAME_FILE + cls.SAME_DICT_PATH

        src = common.split_file_dict_path(src_file_dict_path)
        src_file, src_path = src
        dest = common.split_file_dict_path(dest_file_dict_path)
        dest_file, dest_path = dest
        if src_file == dest_file:
            return cls.SAME_FILE
        if src_path == dest_path:
            return cls.SAME_DICT_PATH
        return 0

    @staticmethod
    def strip_annotations(string):
        """Strip annotations from the given string.

        if the parameter is not a string, it is returned as-is"""
        if not isinstance(string, str):
            return string
        for anno in ('<<A<<', '<<C<<'):
            index = string.find(anno)
            if index != -1:
                string = string[:index]
        return string

    @classmethod
    def match_score(cls, src_file_dict_path, dest_file_dict_path,
                    src_langlabel, dest_langlabel):
        """Return a score indicating how the old and new lang label matches.

        The higher the score, the closer the two lang labels are related.

        If it returns 0, then matching should be forbidden."""

        base_score = cls.base_match_score(src_file_dict_path,
                                          dest_file_dict_path)

        field_perfect = True
        field_score = 0
        for key, value in src_langlabel.items():
            value = cls.strip_annotations(value)
            if not value or value == key:
                continue
            if cls.strip_annotations(dest_langlabel.get(key)) == value:
                field_score += cls.SAME_FIELD
            else:
                field_perfect = False

        if field_score == 0 and not field_perfect:
            return 0
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
                             perfect_score=None):
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
                if score <= 0:
                    continue
                potential_mappings.append((-score,
                                           (src_file_dict_path,
                                            dest_file_dict_path)))
            else:
                for score, mapping in potential_mappings:
                    prio_queue.insert(score, mapping)
        return perfect_matches

    def assign_by_prio_queue(self, prio_queue):
        """Walk into the priority queue and assign those with the best score.

        This unfortunately have to browse through the entire priority queue."""
        for src_file_dict_path, dest_file_dict_path in prio_queue:
            if not self.src.has(src_file_dict_path):
                continue
            if not self.dest.has(dest_file_dict_path):
                continue
            self.assign(src_file_dict_path, dest_file_dict_path, False)

    @staticmethod
    def sort_by_file(string_cache):
        """Return a dict from file_path to a dict from dict_path to lang labels

        i.e. a file_path => (dict_path => lang_label)."""

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
        """Run the entire algorithm, which will:
        - Assign greddily lang labels that didn't change.
        - Try to detect lang labels that moved or were changed within a file.
        - Try to detect lang labels that moved or were changed across files
          (unless no_interfile_move is false).

        Will print statistics on standard output when finished."""
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
        """Write a migration plan as json to a file"""
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
    """Calculate a migration plan from two string caches."""
    source = common.string_cache()
    dest = common.string_cache()
    source.load_from_file(args.source_string_cache)
    dest.load_from_file(args.dest_string_cache)
    migrator = MigrationCalculator(source, dest)
    migrator.do_everything(bool(args.no_file_move))
    migrator.write_json(args.migration_plan)


def migrate_pack(args, plan, sparse_reader, packfile):
    """Migrate a single pack according to a migration plan."""
    result = {}
    for file_dict_path_str, value in packfile.items():
        if file_dict_path_str in plan.unchanged:
            result[file_dict_path_str] = value
            continue
        if file_dict_path_str in plan.to_delete:
            continue

        new_file_dict_path_str = plan.migrate.get(file_dict_path_str)
        if new_file_dict_path_str is None:
            if args.keep_texts:
                result[file_dict_path_str] = value
            else:
                print("Unknown text: %s" % file_dict_path_str)
            continue

        new_orig = sparse_reader.get_str(new_file_dict_path_str)
        if new_orig != value['orig']:
            if args.mark_unknown:
                value["quality"] = "unknown"
            if not args.no_orig:
                value['orig'] = new_orig
        result[new_file_dict_path_str] = value

    return result


def do_migrate(args):
    """Migrate one or more pack file according to a migration file."""
    sorter = get_sorter(args)
    sparse_reader = get_sparse_reader(args)
    plan = common.load_json(args.migration_plan)
    plan = types.SimpleNamespace(to_delete=set(plan["delete"]),
                                 unchanged=set(plan["unchanged"]),
                                 migrate=plan["migrate"])
    iterator = common.transform_file_or_dir(args.inputpath, args.outputpath)
    for input_file, output_file, _ in iterator:
        try:
            src_pack = common.load_json(input_file)
        except OSError as error:
            print("Cannot read", input_file, ":", str(error))
            continue
        except ValueError as error:
            print("File", input_file, "contains invalid JSON:", str(error))
            continue

        dst_pack = migrate_pack(args, plan, sparse_reader, src_pack)

        common.save_json(output_file, sorter(dst_pack))


def parse_args():
    """Parse the command line parameters"""
    import argparse
    parser = argparse.ArgumentParser(description="Command to manage pack"
                                                 " files\n")
    parser.add_argument('--game-dir', '-g', metavar="directory",
                        default='.', dest="gamedir",
                        help="""Location of the installed game's assets/
                        directory. Any subdirectory of it is also accepted.
                        Searchs around the current directory by default.""")
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

    subparsers = parser.add_subparsers(metavar="COMMAND", required=True)

    def add_subcommand(name, function, help, description):
        """A wrapper over subparser that is beautiful and expressive

        It creates a subcommand using a subparser and returns an object with
        an 'option' method that wraps subparser.add_argument().  option() also
        returns the same object, allowing calls to be chained.  option() also
        contains pre-made help text for inputpath, outputpath and bigpack.

        It sure is unpythonic but makes things easier."""
        subparser = subparsers.add_parser(name, help=help,
                                          description=description)
        subparser.set_defaults(func=function)

        ret = types.SimpleNamespace()

        def option(*optnames, **kw):
            if optnames[0] in ("inputpath", "outputpath"):
                kw.setdefault("metavar", "<%s dir or file>" % optnames[0][:-4])
            elif optnames[0] == "bigpack":
                kw.setdefault("metavar", "<big pack>")

            subparser.add_argument(*optnames, **kw)
            return ret

        ret.option = option
        return ret

    (add_subcommand(
        'mkmap', do_make_mapfile, help="create a default map file for 'split'",
        description="""Read a big packfile and write a map file
                       with sensible default values.  The map file can then
                       be customized manually afterward, or can be used
                       with split as-is.""")
     .option("bigpack",
             help="""pack file to use as a template to create the map""")
     .option("--prefix", default="", help="""prefix to use before packs.
             e.g. if specifing mods/mymod/packs, then all small pack will be
             stored as a subdirectory of mods/mymod/packs/""")
     )

    (add_subcommand(
        'split', do_split, help="split a big packfile into small ones",
        description="""Read a big packfile and a map file and
                       write several smaller packfile, controlled by the
                       map file""")
     .option("output", metavar="<output dir>",
             help="""where to write the smaller packs, according to the
                    map file""")
     .option("--strip", "-p", type=int, default=0,
             help="""strip this amount of directories before writing to the
             output. e.g. if the map file references mods/mymod/packs/a, then
             --strip=2 will write it as packs/a in the output directory.""")
     )

    (add_subcommand(
        'merge', do_merge, help="merge several packfiles into a big one",
        description="""Merge all packfiles in a directory into a
                       bigger one.""")
     .option('inputpath', metavar="<input dir>",
             help="""Where to search for packfiles""")
     .option('bigpack', help="""Where to write the big packfile""")
     .option("--allow-mismatch", dest="allow_mismatch", action="store_true",
             help="""If two input pack files possess different translation for
             the same string, then warn and pick the first encountered one.
             The default is to abort in this case.""")
     )

    (add_subcommand(
        'difflang', do_diff_langfile,
        help="Calculate differences between two lang files",
        description="""Given two lang files, calculate the difference as
                       a pack file and write the output.  Lang files are
                       files that typically resides under the lang/
                       directory.""")
     .option("--file-path", dest="filename", metavar="<path of original name",
             help="""Path to use to refer to the difference in the output.
             The default is to use 'lang/sc/<filename>' where filename is
             the name of <original file>""")
     .option("fileorig", metavar="<original file>",
             help="""Original file to use as starting point""")
     .option("filetrans", metavar="<translated file>",
             help="""Translated original file""")
     .option("resultfile", metavar="<output file>",
             help="""Where to write the output.  If '-', then output to the
             standard output""")
     )

    (add_subcommand(
        'calcmigration', do_calcmigrate,
        help="Calculate a migration path from a version to another",
        description="""Given a source string cache and a destination string
                       cache, match source lang labels to destination lang
                       labels using a matching algorithm and write a migration
                       plan to apply later with 'migrate'.  This can be used
                       to updrade packs to the latest version of the game.""")
     .option("source_string_cache", metavar="<source string cache>",
             help="""string cache containing lang labels to migrate from""")
     .option("dest_string_cache", metavar="<destination string cache>",
             help="""string cache containing lang labels to migrate to""")
     .option("migration_plan", metavar="<migration plan>",
             help="""Where to write the migration plan in JSON format""")
     .option("--no-file-move", dest="no_file_move", action="store_true",
             help="""Do not match old lang labels into lang labels in a
             different (game) file.""")
     )

    (add_subcommand(
        'migrate', do_migrate, help="""Apply a migration path to packfiles""",
        description="""Given a pack file or directory and a migration plan,
                       migrate it and write a new pack file or directory.""")
     .option("migration_plan", metavar="<migration plan file>",
             help="Migration plan JSON file as calculated by 'calcmigration'")
     .option("inputpath", help="""pack file or directory to migrate from""")
     .option("outputpath", help="""Where to write migrated pack file(s).
             Setting the same input and output to overwrite it is
             supported.""")
     .option("--no-orig", dest="no_orig", action="store_true",
             help="""Do not update the 'orig' fields in the pack.
             This allows using jsontr afterward to interactively review each
             'orig' change.""")
     .option("--mark-unknown", dest="mark_unknown", action="store_true",
             help="""If the 'orig' field changed, add a quality field with
             value 'unknown', indicating to jsontr or other programs that
             the translation must be reviewed for correctness.""")
     .option("--keep-unknown-texts", dest="keep_texts", action="store_true",
             help="""Do not remove strings that are not present neither in the
             old version nor in the new version of the game.  By default, these
             strings are removed and a warning is logged.""")
     )

    result = parser.parse_args()
    result.func(result)


if __name__ == "__main__":
    parse_args()
