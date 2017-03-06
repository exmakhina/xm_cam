#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# G-code writer
# Legal: see LICENSE file.

import sys, re, io, json, warnings

import numpy as np

class CodeGen(object):
	"""
	G-code generator

	Has an internal state and returns lists of gcodes per command.
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

	cg = CodeGen()

	print(cg.line_to(z=2./3))
	print(cg.line_to(z=1, extruder=4))
	print(cg.rapid_to(x=2))
