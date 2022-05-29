#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# G-code writer
# Legal: see LICENSE file.

import sys, re, io, json, warnings
import logging

import numpy as np


from .feeds_and_speeds import compute_feed_basic

logger = logging.getLogger(__name__)


class PostprocFormatter(object):
	"""
	post-processor that only does simple line-based formatting operations.
	"""

	STRIP_TRAILING_ZEROS = 1<<2
	STRIP_SPACES = 1<<0
	STRIP_COMMENTS = 1<<2
	STRIP_CHECKSUMS = 1<<3
	ADD_CHECKSUM = 1<<10
	ADD_SPACES = 1<<11
	CHECK_COMMENTS = 1<<20
	CHECK_CHECKSUMS = 1<<21

	def __init__(self, println, flags=0):
		self._println = println
		self._flags = flags
		self._donttouch = lambda x: x.startswith("M117")

	def emit(self, *args):
		if len(args) == 1 and (isinstance(args[0], list) or isinstance(args[0], tuple)):
			args = args[0]

		flags = self._flags
		for arg in args:

			if self._donttouch(arg):
				arg = arg.encode("ascii")
				self._println(arg)
				continue

			if (flags & PostprocFormatter.STRIP_COMMENTS) != 0:
				arg = arg.split(";")[0].rstrip()
				try:
					a = arg.index("(")
				except ValueError:
					a = None
				try:
					b = arg.rindex(")")+1
				except ValueError:
					b = None

				if a is not None and b is not None:
					arg = arg[:a].rstrip() + arg[b:].lstrip()
				elif a is None and b is None:
					pass
				elif a is not None and (flags & PostprocFormatter.CHECK_COMMENTS) != 0:
					raise ValueError(arg)
				elif b is not None and (flags & PostprocFormatter.CHECK_COMMENTS) != 0:
					raise ValueError(arg)

			if (flags & PostprocFormatter.STRIP_TRAILING_ZEROS) != 0:
				pass

			if (flags & PostprocFormatter.STRIP_SPACES) != 0:
				arg = arg.replace(" ", "")

			if (flags & PostprocFormatter.ADD_SPACES) != 0:
				arg_out = list()
				last_char = " "
				comment = False
				comment_paren = False
				for idx_char, char in enumerate(arg):
					if char == "(":
						comment_paren = True
					if char == ")":
						comment_paren = False
					if char == ";":
						comment = True
					if (not comment and not comment_paren) \
					 and last_char in "0123456789." \
					 and char in "EFGIJKMXYZS*":
						arg_out.append(" ")
					arg_out.append(char)
					last_char = char
				arg = "".join(arg_out)

			arg = arg.encode("ascii")

			if (flags & PostprocFormatter.ADD_CHECKSUM) != 0 and not b"*" in arg:
				cs = 0
				for x in bytearray(arg):
					cs ^= x
				if (flags & PostprocFormatter.STRIP_SPACES) == 0 or (flags & PostprocFormatter.ADD_SPACES) != 0:
					arg += b" "
				arg += ("*%d" % (cs)).encode("ascii")

			self._println(arg)


class PostprocFormatterStateful(object):
	"""
	Post-processor that doesn't change the meaning of the commands,
	but can perform some operations because it has an internal state.
	"""
	STRIP_REDUNDANT_WORDS = 1<<0 # eg. G91 Z1; G91 Z1 -> G91 Z1; Z1
	STRIP_REDUNDANT_COORDS = 1<<1 # eg. G90; G1 X1 Z1; G1 X1 Z2 -> G90; G1 X1 Z1; G1 Z2

	def __init__(self, println):
		self._println = println
		self._last_x = None
		self._last_y = None
		self._last_z = None
		self._last_f = None
		self._last_e = None
		self._last_absrel = None

	def emit(self, *args):
		pass


class PostprocLevel(object):
	"""
	G-code post-processor that will change XYZ
	"""
	def __init__(self):
		pass



class SegmentInserter(object):
	"""
	Insert intermediate points at a certain time frequency.
	"""




class CodeGen(object):
	"""
	G-code generator

	Has an internal state and returns lists of gcodes per command.

	Notes:

	- Feeds are expressed in mm/min

	- Spaces, which are optional, are output, but they're easy to remove, so it's up to the
	  user to do it.

	- Checksums are not output.

	"""
	def __init__(self):
		self.feed_height = 1
		self.feed = 250
		self.feed_x = 250
		self.feed_y = 500
		self.plunge_feed = 50
		self.raise_feed = 5000
		self.metric = True
		self.curx = float("NaN")
		self.cury = float("NaN")
		self.curz = float("NaN")
		self.curf = float("NaN")
		self.cure = float("NaN")
		self.duration = 0 # seconds
		self.G0_speed = 5000
		self.accuracy = 4 # digits
		self.use_G0 = True
		self.accuracies = dict(
		 E=3,
		 X=3,
		 Y=3,
		 Z=3,
		)
		self.length = 0
		self.duration = 0
		self.fake = False

	def round(self, *args, **kw) -> str:
		"""
		Return the rounded value of each argument,
		with the intent to make the value as short as possible.
		
		Examples:
		
		- 1.0000 -> 1
		- 0.10 -> 0.1
		"""

		accuracy = self.accuracies.get(kw.get("g", None), self.accuracy)

		res = list()
		for arg in args:
			s = json.dumps(round(arg, accuracy))
			if s.endswith(".0"):
				s = str(int(float(s)))
			res.append(s)
		if len(args) == 1:
			return res[0]
		else:
			return res

	def line_to(self, x=None, y=None, z=None,
	 rapid=False, feed=None, f=None, extruder=None, e=None, comment=None):
		"""
		Generate opcodes for a line
		"""
		x = x if x is not None else self.curx
		y = y if y is not None else self.cury
		z = z if z is not None else self.curz

		sx, sy, sz = self.round(x, y, z)

		extruder = e if e is not None else extruder
		feed = f if f is not None else feed

		if extruder is not None:
			self.cure = extruder

		dx = x-self.curx
		dy = y-self.cury
		dz = z-self.curz

		nodx = abs(dx) < 10**(-self.accuracies["X"])
		nody = abs(dy) < 10**(-self.accuracies["Y"])
		nodz = abs(dz) < 10**(-self.accuracies["Z"])

		if nodx and nody and nodz and e is None:
			return []

		if dx == dx and dy == dy and dz == dz:
			self.length += (dx**2+dy**2+dz**2)**0.5

		if rapid:
			if self.use_G0:
				opcode = "G0"
			else:
				opcode = "G1"
			if feed is None:
				feed = self.G0_speed
			assert extruder is None
		else:
			opcode = "G1"
			autofeed = compute_feed_basic(self, dx, dy, dz)

			if feed is not None and feed > autofeed:
				logger.warning("Warning: feed too high from %f %f %f to %f %f %f autofeed %f feed %f\n", self.curx, self.cury, self.curz, x, y, z, autofeed, feed)
				#feed = autofeed

			feed = int(round(feed or autofeed))

		if dx == dx and dy == dy and dz == dz:
			ds = (dx**2+dy**2+dz**2)**0.5
			self.duration += ds / (feed / 60)

		s_x = (" X%s" % (sx)) if (not nodx) else ""
		s_y = (" Y%s" % (sy)) if (not nody) else ""
		s_z = (" Z%s" % (sz)) if (not nodz) else ""
		s_f = (" F%d" % feed) if feed is not None and feed != self.curf else ""
		s_e = (" E%s" % (self.round(extruder, g="E"))) if extruder is not None else ""
		s_d = ""# %f %f %f" % (dx, dy, dz)
		s_c = (" ; %s" % comment) if comment is not None else ""
		res = [
		 opcode + s_x + s_y + s_z + s_f + s_e + s_d + s_c,
		 #f"; dx={dx} dy={dy} dz={dz}",
		]
		if self.fake:
			res = []

		self.curx = float(sx)
		self.cury = float(sy)
		self.curz = float(sz)
		self.curf = feed

		return res


	def rapid_to(self, x=None, y=None, z=None, feed=None):
		return self.line_to(x=x, y=y, z=z, feed=feed, rapid=True)


	# Now fishy stuff

	def xy_line_to(self, x, y, feed=None):
		return self.line_to(x=x, y=y, feed=feed)

	# (endpoint, radius, center, cw?)
	def xy_arc_to(self, x, y, r, cx, cy, cw):
		sx, sy, sr = self.round(x, y, r)
		res = list()
		if (cw):
			res.append("G2 X%s Y%s R%s" % (sx, sy, sr))
		else:
			res.append("G3 X%s Y%s R%s" % (sx, sy, sr))
		# FIXME: optional IJK format arcs
		self.curx = x
		self.cury = y
		if self.fake:
			res = []
		# TODO compute length
		return res

	def xy_rapid_to(self, x,y):
		return self.rapid_to(x=x,y=y)

	def preamble(self, metric=True):
		res = list()

		# Set up unit
		if (metric):
			res.append("G21 F%d" % (self.feed))
		else:
			res.append("G20 F%d" % (self.feed))

		# Default cutting mode
		res.append("G64 P0.001")

		# Go to 0
		res += self.pen_up()
		res.append("G0 X0 Y0")

		# Tool change
		res.append("T1 M06")

		# TBD
		res.append("G17 G90 G21")

		return res

	def postamble(self):
		res = [
		 #"M2", #stop everything
		]
		return res

if __name__ == "__main__":

	def println(x):
		print(b"\x1B[33;1m[" + x + b"]\x1B[0m")

	flags = 0
	flags = PostprocFormatter.STRIP_SPACES
	flags |= PostprocFormatter.STRIP_COMMENTS
	flags |= PostprocFormatter.ADD_CHECKSUM
	flags |= PostprocFormatter.CHECK_COMMENTS
	#flags |= PostprocFormatter.ADD_SPACES
	e = PostprocFormatter(
	 println=println,
	 flags=flags,
	)

	e.emit("G0 X1")
	e.emit("G0 X2", "G0 X3")
	e.emit(("G0 X4", "G0 X5"))
	e.emit(["G0 X6", "G0 X7"])

	cg = CodeGen()

	e.emit(cg.line_to(z=2./3))
	e.emit(cg.line_to(z=1, extruder=4))
	e.emit(cg.rapid_to(x=2))
	e.emit("G0 X8 ; pouet")
	e.emit("G0 X9 ( do something ) ; puoet")
	e.emit("G0 X10 ( do something ) ; puoet")
	try:
		e.emit("G0 X11 ( do something")
		if (flags & PostprocFormatter.CHECK_COMMENTS) != 0:
			raise RuntimeError()
	except ValueError:
		pass
	try:
		e.emit("G0 X12 do something)")
		if (flags & PostprocFormatter.CHECK_COMMENTS) != 0:
			raise RuntimeError()
	except ValueError:
		pass

	e.emit("M117 hello ! yeah; this is sick (very)")
