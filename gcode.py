#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# G-code writer
# Legal: see LICENSE file.

import sys, re, io, json, warnings

import numpy as np

class Emitter(object):
	"""
	g-code post-processor that only does formatting operations
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

			if (flags & Emitter.STRIP_COMMENTS) != 0:
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
				elif a is not None and (flags & Emitter.CHECK_COMMENTS) != 0:
					raise ValueError(arg)
				elif b is not None and (flags & Emitter.CHECK_COMMENTS) != 0:
					raise ValueError(arg)

			if (flags & Emitter.STRIP_TRAILING_ZEROS) != 0:
				pass

			if (flags & Emitter.STRIP_SPACES) != 0:
				arg = arg.replace(" ", "")

			if (flags & Emitter.ADD_SPACES) != 0:
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

			if (flags & Emitter.ADD_CHECKSUM) != 0 and not b"*" in arg:
				cs = 0
				for x in bytearray(arg):
					cs ^= x
				if (flags & Emitter.STRIP_SPACES) == 0 or (flags & Emitter.ADD_SPACES) != 0:
					arg += b" "
				arg += ("*%d" % (cs)).encode("ascii")

			self._println(arg)


class CodeGen(object):
	"""
	G-code generator

	Has an internal state and returns lists of gcodes per command.

	Notes:

	- Spaces, which are optional, are output, but they're easy to remove, so it's up to the
	  user to do it.
	- Checksums are not output.

	"""
	def __init__(self):
		self.feed_height = 1
		self.feed = 250
		self.plunge_feed = 50
		self.raise_feed = 150
		self.metric = True
		self.curx = 0
		self.cury = 0
		self.curz = 0
		self.duration = 0 # seconds
		self.G0_speed = 2000
		self.accuracy = 4 # digits
		self.use_G0 = True

	def round(self, *args):
		"""
		Return the rounded value of each argument,
		with the intent to make the value as short as possible.
		
		Examples:
		
		- 1.0000 -> 1
		- 0.10 -> 0.1
		"""
		res = list()
		for arg in args:
			s = json.dumps(round(arg, self.accuracy))
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

		dx = x-self.curx
		dy = y-self.cury
		dz = z-self.curz

		if dx == 0 and dy == 0 and dz == 0 and e is None:
			return []

		if rapid:
			if self.use_G0:
				opcode = "G0"
				assert feed is None
			else:
				opcode = "G1"
				feed = self.G0_speed
			assert extruder is None
		else:
			opcode = "G1"

			dh = (dx**2+dy**2)**0.5
			dv = abs(dz)
			ds = (dx**2+dy**2+dz**2)**0.5
			if ds != 0:
				fv = self.plunge_feed if dz < 0 else self.raise_feed
				fh = self.feed
				clamp = lambda x, a, b: min(b, max(x, a))
				autofeed = clamp((fv*dv+fh*dh) / ds, fv, fh)
				autofeed = clamp(min(fv*((dh**2+dv**2)**0.5)/(dv+1e-4), fh*((dh**2+dv**2)**0.5)/(dh+1e-4)), fv, fh)
				autofeed = int(round(autofeed))
				feed = int(round(feed or autofeed))
				if feed > autofeed:
					err = "Warning: feed too high from %f %f %f to %f %f %f autofeed %f feed %f\n" % (self.curx, self.cury, self.curz, x, y, z, autofeed, feed)
					warnings.warn(err)

		s_x = (" X%s" % (sx)) if dx != 0 else ""
		s_y = (" Y%s" % (sy)) if dy != 0 else ""
		s_z = (" Z%s" % (sz)) if dz != 0 else ""
		s_f = (" F%d" % feed) if feed is not None else ""
		s_e = (" E%s" % (self.round(extruder))) if extruder is not None else ""
		s_d = ""# %f %f %f" % (dx, dy, dz)
		s_c = (" ; %s" % comment) if comment is not None else ""
		res = [
		 opcode + s_x + s_y + s_z + s_f + s_e + s_d + s_c,
		]

		self.curx = x
		self.cury = y
		self.curz = z

		return res

	def rapid_to(self, x=None, y=None, z=None):
		return self.line_to(x=x, y=y, z=z, rapid=True)


if __name__ == "__main__":

	def println(x):
		print(b"\x1B[33;1m[" + x + b"]\x1B[0m")

	flags = 0
	flags = Emitter.STRIP_SPACES
	flags |= Emitter.STRIP_COMMENTS
	flags |= Emitter.ADD_CHECKSUM
	flags |= Emitter.CHECK_COMMENTS
	#flags |= Emitter.ADD_SPACES
	e = Emitter(
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
		if (flags & Emitter.CHECK_COMMENTS) != 0:
			raise RuntimeError()
	except ValueError:
		pass
	try:
		e.emit("G0 X12 do something)")
		if (flags & Emitter.CHECK_COMMENTS) != 0:
			raise RuntimeError()
	except ValueError:
		pass

	e.emit("M117 hello ! yeah; this is sick (very)")
