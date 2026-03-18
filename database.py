import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional

DB_PATH = "securelink.db"


def _connect():
	return sqlite3.connect(DB_PATH)


def init_db() -> None:
	"""Create the chat_history table if it doesn't exist."""
	conn = _connect()
	cur = conn.cursor()
	cur.execute(
		"""
		CREATE TABLE IF NOT EXISTS chat_history (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			sender TEXT NOT NULL,
			message TEXT NOT NULL,
			timestamp TEXT NOT NULL
		)
		"""
	)
	conn.commit()
	conn.close()


def save_message(sender: str, message: str, timestamp: Optional[str] = None) -> None:
	"""Save a message to the database."""
	if timestamp is None:
		timestamp = datetime.utcnow().isoformat()
	conn = _connect()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO chat_history (sender, message, timestamp) VALUES (?, ?, ?)",
		(sender, message, timestamp),
	)
	conn.commit()
	conn.close()


def load_messages(limit: Optional[int] = None) -> List[Tuple[int, str, str, str]]:
	"""Load previous messages. Returns list of rows (id, sender, message, timestamp).

	If limit is provided, returns only the most recent `limit` rows ordered by id ASC.
	"""
	conn = _connect()
	cur = conn.cursor()
	if limit:
		cur.execute(
			"SELECT id, sender, message, timestamp FROM chat_history ORDER BY id ASC LIMIT ?",
			(limit,),
		)
	else:
		cur.execute("SELECT id, sender, message, timestamp FROM chat_history ORDER BY id ASC")
	rows = cur.fetchall()
	conn.close()
	return rows


if __name__ == "__main__":
	# Quick sanity check when run directly
	init_db()
	save_message("local", "hello from init", None)
	print(load_messages(10))

