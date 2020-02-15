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


def get_sparse_reader(args):
    # TODO: this duplicates code in jsontr.py, should move this into GameWalker
    if os.path.exists(args.string_cache):
        string_cache = common.string_cache(args.from_locale)
        string_cache.load_from_file(args.string_cache)
        return string_cache
    return common.sparse_dict_path_reader(args.gamedir,
                                          args.from_locale)


def do_encrapt(args):
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
        result = common.sort_dict(result)
        common.save_json(output_file, result)
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
        common.save_json(output_file, result)
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
        common.save_json(os.path.join(actual_dir, to_file[-1]), smaller_pack)


def do_merge(args):
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
    if args.sort:
        big_result = common.sort_dict(big_result)

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
    if args.resultfile == '-':
        common.save_json_to_fd(sys.stdout, result)
    else:
        common.save_json(args.resultfile, result)


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
    merge.add_argument("--sort", dest="sort", action="store_true",
                       help="""Sort the entries by ascending path when writing
                               the output file""")
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

    result = parser.parse_args()
    result.func(result)


if __name__ == "__main__":
    parse_args()
