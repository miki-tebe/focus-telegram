# ⚠️ DISCLAIMER ⚠️

Telegram has been very aggressive lately especially with new accounts so use at
your own risk. I have not tested this with new accounts. Telegram may block your
account if you use this script. Test it on an account that you don't mind
losing.

This script is provided as-is without any warranty. Use at your own risk.

# Telegram Focus Mode

Telegram Focus Mode is a Python utility designed to help you regain your focus
by temporarily archiving your Telegram chats. It allows you to "zen out" by
hiding distractions while keeping essential contacts available, and then restore
everything back to normal when you're done.

## Features

- **Focus Mode (Archive)**: Archives all chats to clean up your chat list.
- **Restoration (Unarchive)**: Restores chats to their previous state.
- **Smart Exclusions**: Whitelist specific users, groups, or bots that should
  never be archived.
- **Folder Preservation**: Automatically saves your folder configuration before
  archiving and restores it upon unarchiving.
- **Pin Protection**: Option to keep pinned chats visible (configurable).
- **Batch Processing**: Handles large chat lists efficiently with batching and
  flood wait handling.

## Prerequisites

- Python 3.9 or higher
- A Telegram API ID and API Hash (get them from
  [my.telegram.org](https://my.telegram.org))

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd focus-telegram
   ```

2. **Install dependencies:** This project uses `telethon`. You can install it
   using pip or `uv` (recommended).

   Using `uv`:
   ```bash
   uv sync
   ```

   Using pip:
   ```bash
   pip install telethon
   ```

## Configuration

1. Create a `config.ini` file in the project root (or rename
   `config.ini.example` to `config.ini`).
2. Configure your credentials and preferences:

   ```ini
   [telegram]
   api_id = YOUR_API_ID
   api_hash = YOUR_API_HASH
   session_name = focus_session

   [settings]
   # Set to "true" to keep pinned chats visible, "false" to archive them too.
   ignore_pinned_chats = true

   [exclusions]
   # Comma-separated list of usernames or titles to exclude from archiving.
   # Case-insensitive.
   # @ in username is not required.
   exclude = MyBoss, ImportantGroup, spouse_username
   ```

## Usage

This script is designed to be run via the command line.

### specific commands

**To enter Focus Mode (Archive chats):**

```bash
uv run telegram_focus.py archive
# OR if using pip
python telegram_focus.py archive
```

**To exit Focus Mode (Unarchive chats):**

```bash
uv run telegram_focus.py unarchive
# OR if using pip
python telegram_focus.py unarchive
```

### How it works

1. **Archiving**:
   - The script scans your chat list.
   - It checks against your `[exclusions]` list and `ignore_pinned_chats`
     setting.
   - It saves your current Folder (Dialog Filter) configuration to
     `focus_folders.json` and then removes the folders (so they don't clutter
     the UI with empty tabs).
   - It moves non-excluded chats to the archive.
   - It tracks which chats were archived in `focus_state.json`.

2. **Unarchiving**:
   - It reads `focus_state.json` to know which chats were moved.
   - It restores those specific chats from the archive.
   - It restores your folders from `focus_folders.json`.
   - It cleans up the state files.

## Files

- `telegram_focus.py`: Main script.
- `config.ini`: Configuration file.
- `focus_state.json`: (Generated) Stores IDs of archived chats.
- `focus_folders.json`: (Generated) Stores folder configurations during focus
  mode.
- `*.session`: Telethon session files (keep these secure).

## License

[MIT License](LICENSE)
