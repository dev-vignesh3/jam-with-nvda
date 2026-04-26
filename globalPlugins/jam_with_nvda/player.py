import ctypes
import os
import logging
import ui

# Setup Logging
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Jam_with_NVDA")
LOG_FILE = os.path.join(LOG_DIR, "jam_debug.log")

try:
	if not os.path.exists(LOG_DIR):
		os.makedirs(LOG_DIR)
	logging.basicConfig(
		filename=LOG_FILE,
		level=logging.DEBUG,
		format="%(asctime)s - %(levelname)s - %(message)s",
	)
except (IOError, OSError):
	# If logging fails, we don't want to crash the whole add-on
	pass

logger = logging.getLogger("JamWithNVDA")

# Constants for BASS
BASS_UNICODE = 0x80000000
BASS_ACTIVE_STOPPED = 0
BASS_ACTIVE_PLAYING = 1
BASS_ACTIVE_STALLED = 2
BASS_ACTIVE_PAUSED = 3
BASS_POS_BYTE = 0
BASS_ATTRIB_VOL = 2

class MusicPlayer:
	"""
	A robust music player implementation using the BASS audio engine.
	Supports precise volume control and seeking.
	"""

	def __init__(self):
		self._bass = None
		self._handle = 0
		self._initialized = False
		self._load_bass()

	def _load_bass(self):
		"""Detects architecture and loads the appropriate BASS DLL."""
		is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
		dll_name = "bass_x64.dll" if is_64bit else "bass.dll"
		dll_path = os.path.join(os.path.dirname(__file__), dll_name)

		if not os.path.exists(dll_path):
			logger.error(f"Audio engine files missing at {dll_path}")
			return False

		try:
			self._bass = ctypes.CDLL(dll_path)
			self._setup_prototypes()
			# Initialize BASS (-1 = default device, 44100Hz)
			# Error code 14 is BASS_ERROR_ALREADY, which we can treat as success
			if self._bass.BASS_Init(-1, 44100, 0, None, None) or self._bass.BASS_ErrorGetCode() == 14:
				self._initialized = True
				logger.info("BASS initialized successfully")
				return True
			else:
				logger.error(f"BASS_Init failed with error code: {self._bass.BASS_ErrorGetCode()}")
		except OSError as e:
			logger.error(f"Failed to load BASS DLL: {e}")
		except RuntimeError as e:
			logger.error(f"Runtime error during BASS initialization: {e}")
		return False

	def _setup_prototypes(self):
		"""Configures ctypes function prototypes for BASS."""
		self._bass.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
		self._bass.BASS_Init.restype = ctypes.c_bool
		self._bass.BASS_StreamCreateFile.argtypes = [ctypes.c_bool, ctypes.c_void_p, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_int]
		self._bass.BASS_StreamCreateFile.restype = ctypes.c_uint
		self._bass.BASS_ChannelPlay.argtypes = [ctypes.c_uint, ctypes.c_bool]
		self._bass.BASS_ChannelPlay.restype = ctypes.c_bool
		self._bass.BASS_ChannelPause.argtypes = [ctypes.c_uint]
		self._bass.BASS_ChannelPause.restype = ctypes.c_bool
		self._bass.BASS_ChannelStop.argtypes = [ctypes.c_uint]
		self._bass.BASS_ChannelStop.restype = ctypes.c_bool
		self._bass.BASS_ChannelIsActive.argtypes = [ctypes.c_uint]
		self._bass.BASS_ChannelIsActive.restype = ctypes.c_int
		self._bass.BASS_ChannelSetPosition.argtypes = [ctypes.c_uint, ctypes.c_longlong, ctypes.c_int]
		self._bass.BASS_ChannelSetPosition.restype = ctypes.c_bool
		self._bass.BASS_ChannelGetPosition.argtypes = [ctypes.c_uint, ctypes.c_int]
		self._bass.BASS_ChannelGetPosition.restype = ctypes.c_longlong
		self._bass.BASS_ChannelGetLength.argtypes = [ctypes.c_uint, ctypes.c_int]
		self._bass.BASS_ChannelGetLength.restype = ctypes.c_longlong
		self._bass.BASS_ChannelBytes2Seconds.argtypes = [ctypes.c_uint, ctypes.c_longlong]
		self._bass.BASS_ChannelBytes2Seconds.restype = ctypes.c_double
		self._bass.BASS_ChannelSeconds2Bytes.argtypes = [ctypes.c_uint, ctypes.c_double]
		self._bass.BASS_ChannelSeconds2Bytes.restype = ctypes.c_longlong
		self._bass.BASS_ChannelSetAttribute.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_float]
		self._bass.BASS_ChannelSetAttribute.restype = ctypes.c_bool
		self._bass.BASS_ChannelGetAttribute.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_float)]
		self._bass.BASS_ChannelGetAttribute.restype = ctypes.c_bool
		self._bass.BASS_StreamFree.argtypes = [ctypes.c_uint]
		self._bass.BASS_StreamFree.restype = ctypes.c_bool
		self._bass.BASS_Free.restype = ctypes.c_bool
		self._bass.BASS_ErrorGetCode.restype = ctypes.c_int

	def get_status(self):
		if not self._initialized or not self._handle:
			return "stopped"
		active = self._bass.BASS_ChannelIsActive(self._handle)
		if active == BASS_ACTIVE_PLAYING:
			return "playing"
		elif active == BASS_ACTIVE_PAUSED:
			return "paused"
		return "stopped"

	@property
	def is_playing(self):
		return self.get_status() == "playing"

	@property
	def is_open(self):
		return self._initialized and self._handle != 0

	def get_duration(self):
		if not self._handle:
			return 0.0
		length = self._bass.BASS_ChannelGetLength(self._handle, BASS_POS_BYTE)
		return self._bass.BASS_ChannelBytes2Seconds(self._handle, length)

	def get_position(self):
		if not self._handle:
			return 0.0
		pos = self._bass.BASS_ChannelGetPosition(self._handle, BASS_POS_BYTE)
		return self._bass.BASS_ChannelBytes2Seconds(self._handle, pos)

	def set_position(self, seconds):
		if not self._handle:
			return False
		duration = self.get_duration()
		clamped_seconds = max(0.0, min(duration, seconds))
		byte_pos = self._bass.BASS_ChannelSeconds2Bytes(self._handle, clamped_seconds)
		return self._bass.BASS_ChannelSetPosition(self._handle, byte_pos, BASS_POS_BYTE)

	def set_volume(self, level):
		"""Sets the volume attribute (0.0 to 1.0)."""
		if not self._handle:
			return False
		return self._bass.BASS_ChannelSetAttribute(self._handle, BASS_ATTRIB_VOL, float(level))

	def get_volume(self):
		"""Returns the current volume attribute."""
		if not self._handle:
			return 1.0
		vol = ctypes.c_float()
		if self._bass.BASS_ChannelGetAttribute(self._handle, BASS_ATTRIB_VOL, ctypes.byref(vol)):
			return vol.value
		return 1.0

	def play_file(self, file_path, volume=1.0):
		"""Opens and plays a file with an optional volume level."""
		if not self._initialized:
			if not self._load_bass():
				return False, "Engine not ready"
		
		# Strict Path Validation
		if not os.path.isfile(file_path):
			logger.error(f"File not found: {file_path}")
			return False, "File not found"
		if not os.access(file_path, os.R_OK):
			logger.error(f"File not readable: {file_path}")
			return False, "File not readable"
		
		supported_extensions = ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma')
		if not file_path.lower().endswith(supported_extensions):
			logger.error(f"Unsupported file format: {file_path}")
			return False, "Unsupported format"

		self.stop()
		try:
			path_ptr = ctypes.c_wchar_p(file_path)
			self._handle = self._bass.BASS_StreamCreateFile(False, path_ptr, 0, 0, BASS_UNICODE)
			if self._handle == 0:
				error_code = self._bass.BASS_ErrorGetCode()
				logger.error(f"BASS_StreamCreateFile failed for {file_path} with error {error_code}")
				return False, f"Error {error_code}"
			self.set_volume(volume)
			if self._bass.BASS_ChannelPlay(self._handle, False):
				logger.info(f"Started playing: {file_path}")
				return True, ""
			else:
				logger.error(f"BASS_ChannelPlay failed for {file_path}")
				return False, "Playback failed"
		except (IOError, OSError, RuntimeError) as e:
			logger.error(f"Exception in play_file: {e}")
			return False, str(e)

	def pause(self):
		if not self._handle:
			return False
		return self._bass.BASS_ChannelPause(self._handle)

	def resume(self):
		if not self._handle:
			return False
		return self._bass.BASS_ChannelPlay(self._handle, False)

	def stop(self):
		if self._handle:
			self._bass.BASS_ChannelStop(self._handle)
			self._bass.BASS_ChannelSetPosition(self._handle, 0, BASS_POS_BYTE)
			return True
		return False

	def free(self):
		"""Ensures all BASS resources are released properly."""
		if self._initialized:
			try:
				if self._handle:
					self._bass.BASS_StreamFree(self._handle)
					self._handle = 0
				self._bass.BASS_Free()
				logger.info("BASS resources freed")
			except (IOError, OSError, RuntimeError) as e:
				logger.error(f"Error freeing BASS resources: {e}")
			finally:
				self._initialized = False
				self._bass = None

	def __del__(self):
		"""Destructor to ensure resources are freed when object is destroyed."""
		self.free()
