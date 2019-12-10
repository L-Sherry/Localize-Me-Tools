
def find_tags_database(dict_path, previous):
    tags = ["data-%s"%dict_path[0]]
    if dict_path[0] == "lore":
        tags.append("lore-%s" % previous[2]["category"].lower())
        tags.append("lore-%s"%dict_path[-1])
    elif dict_path[0] == "quests":
        tags.append("quests-%s"%dict_path[-1])
        tags.append("quests-%s"%previous[2].get("area"))
    else:
        tags.append("%s-%s"%(dict_path[0], dict_path[-1]))
    return tags

def find_tags_langfile(file_path, dict_path):
    tags = ["langfile"]
    if not file_path[-1].startswith("gui"):
        return tags
    if dict_path[1:4] == ['menu', 'equip', 'descriptions']:
        if dict_path[-1] != "levels":
            tags.append("equip-description")
    if dict_path[1:4] == ['menu', 'new-game', 'options']:
        tags.append("newgame-%s"%dict_path[4])
    return tags

def try_find_tags_xeno_text(dict_path, previous):
    if dict_path[0] != "entities":
        return None
    if len(dict_path) != 6:
        return None
    if not isinstance(previous[2], dict):
        return None
    if previous[2].get("type") != "XenoDialog":
        return None
    tags = ["xeno"]

    name = previous[-1].get("entity", {}).get("name")
    # now find the npc
    for entity in previous[1]:
        if entity.get("type") != "NPC":
            continue
        settings = entity.get("settings", {})
        if settings.get("name") != name:
            continue

        # found it
        character = settings.get("characterName")
        if character:
            tags.append(character)
        break
    return tags

def find_tags(file_path, dict_path, previous):
    """Find tags to apply to a string given the context of where it was found

    This is very hacky, but does its job most of the time"""
    tags = []

    first_component = file_path[0]
    if first_component.endswith(".json"):
        first_component = first_component[:-5]

    if first_component == "database":
        if dict_path[0] != "commonEvents":
            return find_tags_database(dict_path, previous)
        else:
            tags.append("common-events")
    elif first_component == "item-database":
        return ["item", "item-%s"%dict_path[-1]]
    elif first_component == "lang" and dict_path[0] == 'labels':
        return find_tags_langfile(file_path, dict_path)

    elif first_component == "players" and file_path[1] == "lea.json":
        return ["players-lea-%s"%dict_path[-1]]
    else:
        tags.append("%s-%s"%(first_component, dict_path[-1]))

    if file_path[0] == "maps":
        xenotags = try_find_tags_xeno_text(dict_path, previous)
        if xenotags:
            return tags + xenotags

    # attempts to find all SHOW_MSG and the likes
    if previous and isinstance(previous[-1], dict):

        if previous[-1].get("msgType"):
            # picks up many non-dialogs texts, like new words, tutorials
            type_ = previous[-1].get("msgType").lower()
            tags.append(type_)
            tags.append("%s-%s"%(type_, dict_path[-1]))

        elif previous[-1].get("type"):
            # will pick up pretty much everything else most of the time
            text_type = previous[-1].get("type").lower()
            if text_type.startswith("show_"):
                text_type = text_type[5:]
            if text_type.endswith("_msg"):
                text_type = text_type[:-4]
            tags.append(text_type)
            if text_type in frozenset(("msg", "side")):
                tags.append("conv")
                who = previous[-1].get("person")
                if who:
                    if who.__class__ == str:
                        tags.append(who)
                    else:
                        tags.append(who["person"])
                        tags.append(who["expression"].lower())

    if not tags:
        tags.append("Unknown")

    return tags

BOX_TYPES_BY_TAGS = {
        # quest descriptions in hub menu (exact)
        "quests-location": ('small', 'vbox', 238, 2),
        # approximation for item names (142 comes often, but includes the icon)
        # starts at 116, stops at 122, we really need the space, so ... 122.
        "item-name": ("normal", "hbox", 122, 1),
        # approximation for item description
        # having buffs can incuur a 90px penalty.
        "item-description": ("normal", "hbox", 558, 1),

        # status descriptions could be 290 in status menu
        "equip-description": ("small", "vbox", 290, 2),

        # new game options, not verified, but actually shorter than item names
        "newgame-names": ("normal", "hbox", 124, 1),
        # like item descriptions, but no penalty
        "newgame-descriptions": ("normal", "hbox", 558, 1),

        # another approximation for

        # arts name for lea are 128 normal hbox in status menu....
        # but they are much shorter in circuit menu, more like around 110
        # depending on the translation of the art type.
        "players-lea-name": ("normal", "hbox", 128, 1),
        #"players-lea-name": ("normal", "hbox", 110, 1),

        # achievements:
        # name sems like 240px (295 - 54 according to game).
        "achievements-name": ("normal", "hbox", 239, 1),
        # confirmed
        "achievements-description": ('small', 'box', 224, 2),

        # quest name size ? 206 to 212
        "quests-text": ("normal", "hbox", 206, 1),

        # subtasks in quest menu are 220 max
        "quests-text": ("small", "hbox", 220, 1),
        # quest descriptions are 254 max, 4 lines.
        "quests-description": ("small", "vbox", 254, 4),
        # quest briefing has only 6 lines in the ending dialog box.
        # unconfirmed
        "quests-briefing": ("small", "vbox", 254, 6),

        # xeno dialogs seems to be in a optimized vbox of 140, but no line
        # limit.

        # side msgs are 202 confirmed, max 5 lines, and that's a lot already
        "side": ("normal", "vbox", 202, 5)
}
def get_box_by_tags(tags):
    for tag in tags:
        box = BOX_TYPES_BY_TAGS.get(tag)
        if box is not None:
            return box
    return None
