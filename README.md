# SecureLink — UI & Database (UIDB/ui-database)

This branch implements the "Face" (presentation/UI) and the local storage (database) pieces of SecureLink.

What this part contains

- UI (Presentation Layer)
  - `ui_chat.py` — CustomTkinter-based dashboard UI:
    - Top header with status and a Light/Dark mode switch
    - Sidebar showing active users (auto-discovery is currently simulated)
    - Main chat area with styled message bubbles (green for "me", dark/gray for others)
    - Avatars generated from initials, avatars appear in sidebar and inside message bubbles
    - Multi-line entry box (Enter to send, Shift+Enter for newline)
    - Simple slide-in animation for new messages
    - Demo self-destruct banner on startup

- Database (Network & Data Layer - partial)
  - `database.py` — sqlite3 helpers:
    - `init_db()` — creates `securelink.db` and `chat_history` table
    - `save_message(sender, message, timestamp)` — append a message to DB
    - `load_messages(limit=None)` — load previous messages (ordered by id asc)
  - The DB file `securelink.db` is created in the project root when the app runs.

- Self-destruct helper
  - `self_destruct.py` — `display_then_delete(widget, message, delay=10)`
    - Shows a message in a Tk widget and clears it after the delay (uses `widget.after()` when available).

- Runner
  - `main.py` — small runner that launches `ChatApp`.

Notes and limitations

- Networking and encryption are not implemented in this branch. The UI shows "Encryption: ON" as a status label, but no cryptography is applied yet.
- Auto-discovery is simulated with a background thread that populates the sidebar. Replace `_discover_peers()` in `ui_chat.py` with real UDP/mDNS logic to discover peers.

Dependencies

- Python 3.10+
- customtkinter
- Pillow

These are listed in `requirements.txt`.

How to run

1. Create a virtual environment and install dependencies:

```bash
cd /home/acis/Desktop/securelink-project
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
```

2. Run the app:

```bash
.venv/bin/python main.py
```

- On start the app will create `securelink.db` (if missing) and load any previous messages.
- Send messages from the bottom entry. Outgoing messages are saved to the DB.
- A demo self-destruct banner appears ~2s after startup and clears after 10s.

Troubleshooting

- `pip: command not found` — use the venv pip: `.venv/bin/pip`, or install system pip with `sudo apt install python3-pip` (requires sudo).
- `ModuleNotFoundError: No module named 'tkinter'` — install the system package `python3-tk` (Debian/Ubuntu):
  `sudo apt install python3-tk`
- If `customtkinter` import fails, ensure the venv packages were installed and you run the app with `.venv/bin/python`.

Pushing & Pull Request (notes)

- This branch is `UIDB/ui-database` locally. To push and create a PR to the upstream repo, you need push access to `gaudeltheg/secure_link` or push to your fork and open a PR.
- Example SSH push:

```bash
git remote set-url origin git@github.com:gaudeltheg/secure_link.git
git push -u origin UIDB/ui-database
```

- Example HTTPS push with PAT:

```bash
export GITHUB_TOKEN=ghp_xxx
git push https://$GITHUB_TOKEN@github.com/gaudeltheg/secure_link.git UIDB/ui-database -u
unset GITHUB_TOKEN
```

Next recommended steps

- Implement LAN auto-discovery (UDP broadcast/mDNS) and populate the sidebar from real peers.
- Add Fernet-based encryption so messages stored in `securelink.db` are encrypted at rest.
- Implement the custom packet protocol (`[HEADER]+[SEPARATOR]+[PAYLOAD]`) and the socket send/receive workers.
- Add unit tests for DB helpers and basic integration tests for messaging.

If you want, I can implement any of the next steps for you. If you need me to push and open a PR, follow the push instructions above (SSH or PAT) and paste the push output here if anything fails — I’ll help fix it.
