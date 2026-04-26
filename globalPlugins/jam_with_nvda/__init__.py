import os
import globalPluginHandler
import scriptHandler
import ui
import wx
import gui
from . import player

def format_time(seconds):
	"""Converts seconds into MM:SS format."""
	minutes = int(seconds // 60)
	seconds = int(seconds % 60)
	return f"{minutes:02d}:{seconds:02d}"

class JamDialog(wx.Dialog):
	"""Interactive UI for Jam with NVDA with resolved shortcut conflicts."""
	def __init__(self, parent, plugin):
		# Translators: Title of the Jam with NVDA interface.
		super(JamDialog, self).__init__(parent, title="Jam with NVDA")
		self.plugin = plugin
		
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		# Song Status field
		status_label = "No song loaded"
		if self.plugin.last_song_name:
			status_label = f"Status: {self.plugin.last_song_name}"
		self.statusText = wx.StaticText(self, label=status_label)
		mainSizer.Add(self.statusText, 0, wx.ALL | wx.EXPAND, 15)
		
		self.btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		
		# Play/Pause Toggle Button
		self.playPauseBtn = wx.Button(self, label="&Play")
		self.playPauseBtn.Bind(wx.EVT_BUTTON, self.onPlayPause)
		self.btnSizer.Add(self.playPauseBtn, 0, wx.ALL, 5)

		# Load Song Button (Alt+L)
		self.loadBtn = wx.Button(self, label="&Load Song")
		self.loadBtn.Bind(wx.EVT_BUTTON, self.onLoad)
		self.btnSizer.Add(self.loadBtn, 0, wx.ALL, 5)
		
		# Stop Button (Alt+S)
		self.stopBtn = wx.Button(self, label="&Stop")
		self.stopBtn.Bind(wx.EVT_BUTTON, self.onStop)
		self.btnSizer.Add(self.stopBtn, 0, wx.ALL, 5)

		# Mute/Unmute Button (Alt+U)
		self.muteBtn = wx.Button(self, label="&Mute")
		self.muteBtn.Bind(wx.EVT_BUTTON, lambda e: self.onToggleMute())
		self.btnSizer.Add(self.muteBtn, 0, wx.ALL, 5)

		# Minimize Button (Alt+M)
		self.minimizeBtn = wx.Button(self, label="&Minimize")
		self.minimizeBtn.Bind(wx.EVT_BUTTON, self.onMinimize)
		self.btnSizer.Add(self.minimizeBtn, 0, wx.ALL, 5)

		# Stop and Exit Jam Button (Alt+X)
		self.exitBtn = wx.Button(self, label="Stop and E&xit")
		self.exitBtn.Bind(wx.EVT_BUTTON, self.onStopAndExit)
		self.btnSizer.Add(self.exitBtn, 0, wx.ALL, 5)
		
		mainSizer.Add(self.btnSizer, 0, wx.CENTER | wx.ALL, 10)
		
		self.SetSizer(mainSizer)
		mainSizer.Fit(self)
		
		# Global Key Hooks within the dialog
		self.Bind(wx.EVT_CHAR_HOOK, self.onKeyDown)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		
		# Initial state and focus
		self.update_ui_state(initial=True)

	def onKeyDown(self, event):
		"""Intercepts specific playback keys while allowing mnemonics to pass."""
		try:
			keyCode = event.GetKeyCode()
			if keyCode == wx.WXK_SPACE:
				self.onPlayPause(None)
				return
			elif keyCode == wx.WXK_ESCAPE or keyCode == ord('M') or keyCode == ord('m'):
				if not event.AltDown() and not event.ControlDown():
					self.onMinimize(None)
					return
			elif self.plugin.player and self.plugin.player.is_open:
				if keyCode == wx.WXK_RIGHT:
					seek_time = 30 if event.ShiftDown() else 5
					self.onSeek(seek_time)
					return
				elif keyCode == wx.WXK_LEFT:
					seek_time = -30 if event.ShiftDown() else -5
					self.onSeek(seek_time)
					return
				elif keyCode == wx.WXK_UP:
					vol_step = 0.10 if event.ShiftDown() else 0.05
					self.onAdjustVolume(vol_step)
					return
				elif keyCode == wx.WXK_DOWN:
					vol_step = -0.10 if event.ShiftDown() else -0.05
					self.onAdjustVolume(vol_step)
					return
				elif keyCode == ord('U') or keyCode == ord('u'):
					if not event.AltDown() and not event.ControlDown():
						self.onToggleMute()
						return
				elif keyCode == ord('T') or keyCode == ord('t'):
					if not event.AltDown() and not event.ControlDown():
						self.announce_time_status()
						return
			
			event.Skip()
		except Exception:
			event.Skip()

	def onSeek(self, offset):
		current_pos = self.plugin.player.get_position()
		duration = self.plugin.player.get_duration()
		new_pos = current_pos + offset
		if new_pos >= duration:
			self.onStop(None)
			ui.message("Reached end of song")
			return
		if self.plugin.player.set_position(new_pos):
			ui.message(format_time(new_pos))

	def onAdjustVolume(self, step):
		new_vol = max(0.0, min(1.0, self.plugin.volume + step))
		self.plugin.volume = new_vol
		self.plugin.is_muted = False
		self.muteBtn.SetLabel("&Mute")
		if self.plugin.player:
			self.plugin.player.set_volume(new_vol)
		ui.message(f"Volume {int(new_vol * 100)}%")

	def onToggleMute(self):
		"""Toggles mute state."""
		if self.plugin.is_muted:
			self.plugin.is_muted = False
			vol = self.plugin.volume
			self.muteBtn.SetLabel("&Mute")
			ui.message(f"Unmuted, Volume {int(vol * 100)}%")
		else:
			self.plugin.is_muted = True
			vol = 0.0
			self.muteBtn.SetLabel("&Unmute")
			ui.message("Muted")
		
		if self.plugin.player:
			self.plugin.player.set_volume(vol)

	def announce_time_status(self):
		current = format_time(self.plugin.player.get_position())
		total = format_time(self.plugin.player.get_duration())
		ui.message(f"{current} of {total}")

	def update_ui_state(self, initial=False):
		if not self.plugin.player:
			return
		is_loaded = self.plugin.player.is_open
		status = self.plugin.player.get_status()
		self.playPauseBtn.Show(is_loaded)
		self.stopBtn.Show(is_loaded)
		self.minimizeBtn.Show(is_loaded)
		self.muteBtn.Show(is_loaded)
		self.loadBtn.Show(not is_loaded)
		self.exitBtn.Show(True)
		if is_loaded:
			self.playPauseBtn.SetLabel("&Pause" if status == "playing" else "&Play")
			self.muteBtn.SetLabel("&Unmute" if self.plugin.is_muted else "&Mute")
		self.Layout()
		if initial:
			if is_loaded:
				self.playPauseBtn.SetFocus()
			else:
				self.loadBtn.SetFocus()

	def onLoad(self, event):
		if self.plugin.player and self.plugin.player.is_playing:
			ui.message("Action blocked: Stop music first")
			return
		try:
			with wx.FileDialog(self, "Select Audio", wildcard="Audio Files|*.mp3;*.wav;*.ogg", style=wx.FD_OPEN) as fd:
				if fd.ShowModal() == wx.ID_CANCEL:
					return
				path = fd.GetPath()
				vol = 0.0 if self.plugin.is_muted else self.plugin.volume
				success, msg = self.plugin.player.play_file(path, volume=vol)
				if success:
					self.plugin.last_song_path = path
					self.plugin.last_song_name = fd.GetFilename()
					self.statusText.SetLabel(f"Status: Playing {self.plugin.last_song_name}")
					ui.message("Song loaded")
					self.update_ui_state()
					if self.playPauseBtn.IsShown():
						self.playPauseBtn.SetFocus()
				else:
					ui.message(f"Load failed: {msg}")
		except Exception as e:
			ui.message(f"Error: {e}")

	def onPlayPause(self, event):
		self.plugin.toggle_playback_logic()
		self.update_ui_state()

	def onStop(self, event):
		try:
			if self.plugin.player:
				self.plugin.player.stop()
				self.statusText.SetLabel("Status: Stopped")
				ui.message("Music stopped")
				self.update_ui_state()
				if self.loadBtn.IsShown():
					self.loadBtn.SetFocus()
		except Exception as e:
			ui.message(f"UI Error: {e}")

	def onMinimize(self, event):
		"""Closes UI and keeps playback."""
		ui.message("Jam Minimized")
		self.Destroy()
		self.plugin._dialog = None

	def onStopAndExit(self, event):
		if self.plugin.player:
			self.plugin.player.free()
			self.plugin.player = None
		self.plugin.last_song_path = None
		self.plugin.last_song_name = None
		ui.message("Jam Mode exited")
		self.Destroy()
		self.plugin._dialog = None

	def onClose(self, event):
		self.onMinimize(None)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self.player = None
		self._dialog = None
		self.last_song_path = None
		self.last_song_name = None
		self.volume = 1.0
		self.is_muted = False
		wx.CallLater(500, ui.message, "Jam session started")

	def _ensure_player_initialized(self):
		"""Instantiates the Player class and initializes BASS if not already done."""
		if self.player is None:
			try:
				self.player = player.MusicPlayer()
				return True
			except Exception:
				ui.message("Failed to initialize engine")
				return False
		return True

	def toggle_playback_logic(self):
		if not self._ensure_player_initialized():
			return

		if not self.player or not self.player.is_open:
			if self.last_song_path:
				vol = 0.0 if self.is_muted else self.volume
				success, msg = self.player.play_file(self.last_song_path, volume=vol)
				if success:
					ui.message(f"Playing {self.last_song_name}")
					return
			ui.message("No song loaded")
			return
		status = self.player.get_status()
		if status == "playing":
			if self.player.pause():
				ui.message("Music Paused")
		else:
			if self.player.resume():
				ui.message("Music Playing")

	def script_togglePlayback(self, gesture):
		self.toggle_playback_logic()
		if self._dialog:
			wx.CallAfter(self._dialog.update_ui_state)

	def script_toggleJamMode(self, gesture):
		if self._dialog:
			self._dialog.Raise()
			self._dialog.SetFocus()
			return
		if self._ensure_player_initialized():
			wx.CallAfter(self._show_gui)

	def _show_gui(self):
		self._dialog = JamDialog(gui.mainFrame, self)
		self._dialog.Show()
		self._dialog.Raise()

	def terminate(self):
		if self.player:
			self.player.free()
		super(GlobalPlugin, self).terminate()

	# Translators: Description for Jam Mode toggle script.
	script_toggleJamMode.__doc__ = "Opens the Jam with NVDA interface."
	# Translators: Description for Global Playback Toggle script.
	script_togglePlayback.__doc__ = "Toggles music playback globally."
	
	__gestures = {
		"kb:nvda+shift+j": "toggleJamMode",
		"kb:nvda+j": "togglePlayback",
	}
