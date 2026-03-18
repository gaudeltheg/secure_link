<<<<<<< HEAD
# secure_link
Implementation of LAN, SecLink is a lightweight, privacy-focused chat application that ensures secure communication over local networks. Built with Python, it features end-to-end encryption, auto-discovery of peers, and secure file transfer capabilities, ensuring your data never leaves your control.
=======
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
     # secure_link — UI & Database (UIDB/ui-database)

    Implementation note: SecureLink is a LAN chat prototype. This branch focuses on the presentation layer ("Face") and local storage.

    What this branch contains

    - UI (Presentation Layer)
      - `ui_chat.py` — CustomTkinter-based dashboard UI:
        - Header with status and Light/Dark mode switch
        - Sidebar showing active users (auto-discovery currently simulated)
        - Chat area with styled message bubbles (green for "me", dark/gray for others)
        - Avatars generated from initials, appearing in sidebar and inside message bubbles
        - Multi-line entry box (Enter to send, Shift+Enter for newline)
        - Slide-in animation for new messages
        - Demo self-destruct banner on startup

    - Database (partial)
      - `database.py` — sqlite3 helpers:
        - `init_db()` — creates `securelink.db` and `chat_history` table
        - `save_message(sender, message, timestamp)` — append a message to DB
        - `load_messages(limit=None)` — load previous messages (ordered by id asc)
      - The DB file `securelink.db` is created in the project root when the app runs.

    - Self-destruct helper
      - `self_destruct.py` — `display_then_delete(widget, message, delay=10)` — shows a message and clears it after a delay (uses `widget.after()` when available).

    - Runner
      - `main.py` — small runner that launches `ChatApp`.

    Notes and limitations

    - Networking and encryption are not yet implemented in this branch. The UI shows "Encryption: ON" as a status label for demo purposes only.
    - Auto-discovery is simulated; replace `_discover_peers()` in `ui_chat.py` with real UDP/mDNS logic to discover peers.

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

    - On start the app will create `securelink.db` (if missing) and load previous messages.
    - Send messages from the bottom entry; outgoing messages are saved to the DB.
    - A demo self-destruct banner appears ~2s after startup and clears after 10s.

    Troubleshooting

    - `pip: command not found` — use the venv pip: `.venv/bin/pip`, or install system pip with `sudo apt install python3-pip` (requires sudo).
    - `ModuleNotFoundError: No module named 'tkinter'` — install `python3-tk` (Debian/Ubuntu):
      ```bash
      sudo apt install python3-tk
      ```
    - If `customtkinter` import fails, ensure the venv packages were installed and you run the app with `.venv/bin/python`.

    Pushing & Pull Request (notes)

    - Branch: `UIDB/ui-database` (source). When a PR is created this branch's changes will be proposed to the target branch on the remote repo.
    - To push from this machine (HTTPS with PAT):

    ```bash
    export GITHUB_TOKEN=ghp_xxx
    git push https://$GITHUB_TOKEN@github.com/gaudeltheg/secure_link.git UIDB/ui-database -u
    unset GITHUB_TOKEN
    ```

    Next recommended steps

    - Implement LAN auto-discovery (UDP broadcast/mDNS) and populate the sidebar from real peers.
    - Add encryption for messages at rest (Fernet) and in transit.
    - Implement the custom packet protocol (`[HEADER]+[SEPARATOR]+[PAYLOAD]`) and socket workers.
    - Add unit tests for DB helpers and integration tests for messaging.

    If you want, I can implement any of the next steps or help create the PR. After creating the PR you can add reviewers and CI will run if configured.
