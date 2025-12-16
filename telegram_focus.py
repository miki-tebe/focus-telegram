# /// script
# requires-python = ">=3.9"
# dependencies = ["telethon"]
# ///

import sys
import os
import json
import asyncio
import logging
import tempfile
import shutil
from typing import List, Set, Any
from configparser import ConfigParser, Error as ConfigError
from telethon import TelegramClient, utils
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import (
    GetDialogFiltersRequest,
    UpdateDialogFilterRequest,
    UpdateDialogFiltersOrderRequest,
)
from telethon.tl.types import (
    DialogFilter,
    DialogFilterChatlist,
    TextWithEntities,
    TypeInputPeer,
)

# ====== LOGGING ======
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
# =====================

# ====== CONSTANTS ======
TRACKING_FILE = "focus_state.json"
FOLDERS_FILE = "focus_folders.json"
BATCH_SIZE = 30
# =======================


def load_config() -> tuple[TelegramClient, List[str], bool]:
    """Load configuration and return client, exclusion list, and pinned setting."""
    config = ConfigParser()
    if not os.path.exists("config.ini"):
        logger.error("config.ini not found!")
        sys.exit(1)

    try:
        config.read("config.ini")
        api_id = config.getint("telegram", "api_id")
        api_hash = config.get("telegram", "api_hash")
        session_name = config.get("telegram", "session_name")

        # Exclusion list
        exclude_str = config.get("exclusions", "exclude", fallback="")
        exclude_list = [x.strip() for x in exclude_str.split(",") if x.strip()]

        # Pinned setting
        ignore_pinned = config.getboolean(
            "settings", "ignore_pinned_chats", fallback=True
        )

        client = TelegramClient(session_name, api_id, api_hash)
        return client, exclude_list, ignore_pinned

    except (ConfigError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)


# Initialize globals
client, EXCLUDE_LIST, IGNORE_PINNED = load_config()


def should_exclude(dialog):
    """Return True if dialog should be skipped."""
    if IGNORE_PINNED and dialog.pinned:
        return True

    ent = getattr(dialog, "entity", None)
    dialog_id = getattr(dialog, "id", None)
    username = getattr(ent, "username", None) if ent else None
    title = getattr(dialog, "title", getattr(dialog, "name", None))

    for ex in EXCLUDE_LIST:
        if isinstance(ex, int) and dialog_id == ex:
            return True
        if isinstance(ex, str):
            if username and username.lower() == ex.lower():
                return True
            if title and title.lower() == ex.lower():
                return True
    return False


def atomic_write_json(filepath: str, data: Any):
    """Write data to a JSON file atomically."""
    dir_name = os.path.dirname(filepath) or "."
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=dir_name, delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp, indent=2)
            temp_name = tmp.name

        shutil.move(temp_name, filepath)
    except Exception as e:
        logger.error(f"Error saving file {filepath}: {e}")
        if os.path.exists(temp_name):
            os.remove(temp_name)


def load_tracked_chats() -> Set[int]:
    """Load tracked chat IDs from the state file."""
    if not os.path.exists(TRACKING_FILE):
        return set()
    try:
        with open(TRACKING_FILE, "r") as f:
            data = json.load(f)
            return set(data)
    except Exception as e:
        logger.error(f"Error loading state file: {e}")
        return set()


def save_tracked_chats(chat_ids: List[int]):
    """Save tracked chat IDs to the state file."""
    existing = load_tracked_chats()
    updated = existing.union(chat_ids)
    atomic_write_json(TRACKING_FILE, list(updated))


def clear_tracked_chats():
    """Clear the state file."""
    try:
        if os.path.exists(TRACKING_FILE):
            os.remove(TRACKING_FILE)
    except OSError as e:
        logger.error(f"Error removing tracking file: {e}")


def serialize_peer(peer):
    """Convert a Peer object to a simple ID."""
    return utils.get_peer_id(peer)


async def resolve_ids_to_peers(ids: List[int]) -> List[TypeInputPeer]:
    """Resolve a list of IDs to InputPeer objects."""
    peers = []
    for peer_id in ids:
        try:
            entity = await client.get_input_entity(peer_id)
            peers.append(entity)
        except Exception as e:
            logger.warning(f"Could not resolve peer {peer_id}: {e}")
    return peers


async def save_folders():
    """Save all dialog filters (folders) to a file and delete them."""
    try:
        result = await client(GetDialogFiltersRequest())
        filters = getattr(result, "filters", result)  # Fallback if it is somehow a list
        serialized_filters = []

        if not hasattr(filters, "__iter__"):
            print(f"Error: Filters object is not iterable: {type(filters)}")
            return

        for f in filters:
            if isinstance(f, DialogFilter):
                f_type = "DialogFilter"
            elif isinstance(f, DialogFilterChatlist):
                f_type = "DialogFilterChatlist"
            else:
                continue

            # Common fields
            pinned = [utils.get_peer_id(p) for p in f.pinned_peers]
            included = [utils.get_peer_id(p) for p in f.include_peers]

            f_data = {
                "type": f_type,
                "id": f.id,
                "title": f.title if not hasattr(f.title, "text") else f.title.text,
                "emoticon": f.emoticon,
                "pinned_peers": pinned,
                "include_peers": included,
            }

            if f_type == "DialogFilter":
                excluded = [utils.get_peer_id(p) for p in f.exclude_peers]
                f_data.update(
                    {
                        "contacts": f.contacts,
                        "non_contacts": f.non_contacts,
                        "groups": f.groups,
                        "broadcasts": f.broadcasts,
                        "bots": f.bots,
                        "exclude_muted": f.exclude_muted,
                        "exclude_read": f.exclude_read,
                        "exclude_archived": f.exclude_archived,
                        "exclude_peers": excluded,
                    }
                )
            elif f_type == "DialogFilterChatlist":
                f_data.update({"has_my_invites": f.has_my_invites})

            serialized_filters.append(f_data)

        if not serialized_filters:
            return

        atomic_write_json(FOLDERS_FILE, serialized_filters)

        logger.info(f"Saved {len(serialized_filters)} folders.")

        # Delete folders
        for folder_data in serialized_filters:
            await client(UpdateDialogFilterRequest(id=folder_data["id"], filter=None))
        logger.info("Required folders removed.")

    except Exception as e:
        logger.error(f"Error handling folders: {e}")


async def restore_folders():
    """Restore folders from file."""
    if not os.path.exists(FOLDERS_FILE):
        return

    try:
        with open(FOLDERS_FILE, "r") as f:
            data = json.load(f)

        for f_data in data:
            # Resolve peers
            pinned = await resolve_ids_to_peers(f_data["pinned_peers"])
            included = await resolve_ids_to_peers(f_data["include_peers"])

            title = f_data["title"]
            if isinstance(title, str):
                title = TextWithEntities(text=title, entities=[])

            f_type = f_data.get(
                "type", "DialogFilter"
            )  # Default for backward compatibility if any

            if f_type == "DialogFilter":
                excluded = await resolve_ids_to_peers(f_data["exclude_peers"])
                new_filter = DialogFilter(
                    id=f_data["id"],
                    title=title,
                    pinned_peers=pinned,
                    include_peers=included,
                    exclude_peers=excluded,
                    contacts=f_data.get("contacts", False),
                    non_contacts=f_data.get("non_contacts", False),
                    groups=f_data.get("groups", False),
                    broadcasts=f_data.get("broadcasts", False),
                    bots=f_data.get("bots", False),
                    exclude_muted=f_data.get("exclude_muted", False),
                    exclude_read=f_data.get("exclude_read", False),
                    exclude_archived=f_data.get("exclude_archived", False),
                    emoticon=f_data.get("emoticon", ""),
                )
            elif f_type == "DialogFilterChatlist":
                new_filter = DialogFilterChatlist(
                    id=f_data["id"],
                    title=title,
                    pinned_peers=pinned,
                    include_peers=included,
                    emoticon=f_data.get("emoticon", ""),
                    has_my_invites=f_data.get("has_my_invites", False),
                )
            else:
                print(f"Unknown filter type: {f_type}")
                continue

            await client(UpdateDialogFilterRequest(id=new_filter.id, filter=new_filter))
        logger.info(f"Restored {len(data)} folders.")

        # Restore order
        # The list 'data' is loaded from JSON which preserves order of insertion/list.
        # We assume the user wants them in that saved order.
        ordered_ids = [d["id"] for d in data]
        if ordered_ids:
            try:
                await client(UpdateDialogFiltersOrderRequest(order=ordered_ids))
                logger.info("Restored folder order.")
            except Exception as e:
                logger.error(f"Error restoring folder order: {e}")

        if os.path.exists(FOLDERS_FILE):
            os.remove(FOLDERS_FILE)

    except Exception as e:
        logger.error(f"Error restoring folders: {e}")


async def move_dialogs(archive=True):
    """
    Archive or unarchive dialogs in batches.
    - archive=True: archive non-excluded, non-archived dialogs
    - archive=False: unarchive archived, non-excluded dialogs (only if previously tracked)
    """
    folder_id = 1 if archive else 0
    target_archived = (
        not archive
    )  # archived=False when archiving, True when unarchiving

    tracked_ids = set()
    if not archive:
        tracked_ids = load_tracked_chats()
        # Only return if we ALSO have no folders to restore
        if not tracked_ids and not os.path.exists(FOLDERS_FILE):
            logger.info("No tracked chats or folders to restore.")
            return

    to_move = []
    ids_to_track = []

    async for dialog in client.iter_dialogs(archived=target_archived):
        if should_exclude(dialog):
            logger.debug(f"Skipping (excluded): {dialog.title}")
            continue

        # If unarchiving, skip if not in our tracked list
        if not archive and dialog.id not in tracked_ids:
            continue

        to_move.append(dialog.entity)
        if archive:
            ids_to_track.append(dialog.id)

    if not to_move:
        logger.info(f"No dialogs to {'archive' if archive else 'unarchive'}.")
        if not archive:
            await restore_folders()
            # If we had no chats but maybe folders, we should still clear tracked chats (which were empty anyway)
            # but mainly we rely on restore_folders to clear its own file.
        return

    logger.info(f"{len(to_move)} dialogs to {'archive' if archive else 'unarchive'}.")

    if archive:
        save_tracked_chats(ids_to_track)
        await save_folders()

    # Process in batches
    for i in range(0, len(to_move), BATCH_SIZE):
        batch = to_move[i : i + BATCH_SIZE]
        try:
            await client.edit_folder(batch, folder=folder_id)
            logger.info(
                f"{'Archived' if archive else 'Unarchived'} {len(batch)} dialogs"
            )
        except FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            # retry after waiting
            await client.edit_folder(batch, folder=folder_id)

    if not archive:
        await restore_folders()
        clear_tracked_chats()


async def main():
    if len(sys.argv) < 2:
        print("Usage: uv run telegram_focus.py [archive|unarchive]")
        return

    mode = sys.argv[1].lower()
    if mode == "archive":
        await move_dialogs(archive=True)
    elif mode == "unarchive":
        await move_dialogs(archive=False)
    else:
        print("Invalid option. Use: archive or unarchive")


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
