import threading
import time
from typing import Any


def display_then_delete(widget: Any, message: str, delay: int = 10) -> None:
	"""Display `message` in the given Tk widget, wait `delay` seconds, then clear it.

	This helper supports common Tk widgets:
	- Label/CTkLabel: widget.configure(text=...)
	- Text/Text widget: widget.delete('1.0', 'end')
	- Entry: widget.delete(0, 'end')

	It uses the widget.after method when available (preferred for mainloop safety).
	"""

	def _set_text():
		try:
			# Label-like
			widget.configure(text=message)
		except Exception:
			try:
				# Text-like widget
				widget.delete("1.0", "end")
				widget.insert("1.0", message)
			except Exception:
				try:
					# Entry-like
					widget.delete(0, "end")
					widget.insert(0, message)
				except Exception:
					# Best effort: set an attribute
					setattr(widget, "text", message)

	def _clear_text():
		try:
			widget.configure(text="")
		except Exception:
			try:
				widget.delete("1.0", "end")
			except Exception:
				try:
					widget.delete(0, "end")
				except Exception:
					try:
						setattr(widget, "text", "")
					except Exception:
						pass

	# Run on the Tk mainloop if available
	try:
		widget.after(0, _set_text)
		widget.after(delay * 1000, _clear_text)
	except Exception:
		# Fallback to a background thread (not ideal for Tk but safe fallback)
		def _thread_job():
			_set_text()
			time.sleep(delay)
			_clear_text()

		t = threading.Thread(target=_thread_job, daemon=True)
		t.start()

