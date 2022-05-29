#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# PYTHON_ARGCOMPLETE_OK
# g-code sender

import sys, io, os
import re
import time
import subprocess
import collections
import logging
import contextlib
import shlex

from ..konvini.subprocess import (
 TerminatingPopen,
)

logger = logging.getLogger(__name__)

class Pipe(object):
	"""
	TCP connector
	"""
	def __init__(self, stdin=None, stdout=None, endline=b"\n"):
		self.stdin = stdin
		self.stdout = stdout
		self.verbose = True
		self._endline = endline
		logger.debug("endline: “%s”", endline)

	def readline(self, timeout=None):
		"""
		"""

		buf = io.BytesIO()
		while not buf.getvalue().endswith(self._endline):
			data = self.stdout.read(1)
			buf.write(data)
		return buf.getvalue()[:-len(self._endline)].decode("utf-8")

	def sendline(self, l):
		pkt = l.encode() + self._endline
		x = self.stdin.write(pkt)
		self.stdin.flush()
		return x # len(pkt)


class SenderGrbl(object):
	"""
	"""
	queue_full_retry = 0.3

	def __init__(self, pipe=None, stdin=None, stdout=None, version="1.1"):
		if pipe is None:
			self.pipe = pipe = Pipe(stdin=stdin, stdout=stdout, endline=b"\r\n")
		# Initialize
		self.verbose = verbose = True
		self._version = version
		self._bufsize = 128 - 30 # keep room for values entered manually out of band
		self._bufavail = self._bufsize

	def open(self, initial=True):
		p = self.pipe
		if initial:
			logger.info("Initializing grbl...")
			p.sendline("")
			p.sendline("")
			while True:
				res = p.readline()
				if res is None:
					break
				logger.info("\x1B[32m%s\x1B[0m", res)


	def queue(self, line):
		p = self.pipe

		if line != "?":
			if self._version == "0.9":
				can_send = lambda x: x["cmdbuf"] < 10 and x["rxbuf"] < 100
			elif self._version == "1.1":
				can_send = lambda x: x["cmdbuf"] > 2 and x["rxbuf"] > (5 + len(line))
			self.wait_status(condition=can_send, poll_delay=self.queue_full_retry)

		logger.info("\x1B[33mNow sending %s\x1B[0m", line)
		p.sendline(line)


		while True:
			res = p.readline()
			#if res == "":
			#	print("\x1B[31mEmpty line?\x1B[0m")
			#	continue
			if res is None:
				time.sleep(0.1)
				continue
			if re.match(r"\[.*\]", res):
				self.last_notice = res
				logger.info("\x1B[32m%s\x1B[0m", res)
				continue
			if re.match(r"<.*>", res):
				self.last_status = res
				logger.info("\x1B[32m%s\x1B[0m", res)
				continue
			break

		logger.info("\x1B[32m%s\x1B[0m", res)
		assert res == "ok", res

		if line == "M2":
			"""
			grbl outputs extra info when M2 is said
			"""
			logger.info("\x1B[31mM2\x1B[0m")
			x = p.readline()
			logger.info("\x1B[32m%s\x1B[0m", x)
			x = p.readline()
			logger.info("\x1B[32m%s\x1B[0m", x)
			x = p.readline()
			logger.info("\x1B[32m%s\x1B[0m", x)
			x = p.readline()
			logger.info("\x1B[32m%s\x1B[0m", x)

		return res

	def wait_status(self, condition=None, poll_delay=1.0):
		if condition is None:
			condition = lambda x: x["cmdbuf"] == 0

		while True:
			status = self.status()
			if condition(status):
				break
			time.sleep(poll_delay)

	def status(self):
		p = self.pipe
		self.last_status = None
		res = self.queue("?")
		while self.last_status is None:
			res = p.readline()
			if res is None:
				time.sleep(0.1)
				continue
			if re.match(r"\[.*\]", res):
				self.last_notice = res
				logger.info("\x1B[32m%s\x1B[0m", res)
				continue
			if re.match(r"<.*>", res):
				self.last_status = res
				logger.info("\x1B[32m%s\x1B[0m", res)
				continue

		if self._version == "1.1":
			m = re.match(r"<(?P<state>[A-Za-z:0-9]+)(\|((MPos:(?P<mpos>[-\d.,]+))|(WPos:(?P<wpos>[-\d.,]+))|(WCO:[-\d.,]+)|(Bf:(?P<cmdbuf>\d+),(?P<rxbuf>\d+))|(Ln:(?P<ln>\d+))|(F:(?P<feed1>\d+))|(FS:(?P<feed2>\d+),(?P<sfeed>\d+))|(Pn:(?P<pins>\S+))|(Ov:(?P<ovf>\S+),(?P<ovr>\S+),(?P<ovs>\S+))|(\|A:\S+)))+>", self.last_status)
		elif self._version == "0.9":
			m = re.match(r"<(?P<state>\S+),MPos:(?P<mpos>\S+),WPos:(?P<wpos>\S+),Buf:(?P<cmdbuf>\S+),RX:(?P<rxbuf>\S+),Ln:(?P<ln>\S+),F:(?P<feed>\S+)\.>", self.last_status)

		assert m is not None

		#print(m.groups())

		res = dict(
		 state=m.group("state"),
		 cmdbuf=int(m.group("cmdbuf")),
		 rxbuf=int(m.group("rxbuf")),
		)

		return res


class SenderTrinus(object):

	def __init__(self, pipe=None, stdin=None, stdout=None):
		if pipe is None:
			self.pipe = pipe = Pipe(stdin=stdin, stdout=stdout, endline=b"\n")
		# Initialize
		self.verbose = verbose = True
		self._last_notices = collections.deque()

	def open(self, initial=True):
		p = self.pipe
		if initial:
			logger.info("Initializing TODO...")
			p.sendline("")
			p.sendline("")
			while True:
				res = p.readline()
				if res is None:
					break
				logger.info("\x1B[32m%s\x1B[0m", res)

	def queue(self, line):
		p = self.pipe

		def shorten(line):
			line = line.split(";")[0].rstrip()

			if line in (
			 "G21",
			 "G90",
			 "M82",
			 "M600", # Filament change
			 ):
				# Unsupported commands
				return
			if line.startswith("M117"):
				return line

			if not "*" in line:
				# Apply checksum
				s = ("%s " % line).encode("utf-8")
				cs = 0
				for v in bytearray(s):
					cs = cs ^ v
				cs = cs & 0xff
				return "%s *%d" % (line, cs)

		out = shorten(line)

		if out is None:
			return

		while True:
			logger.info("\x1B[33m> %s\x1B[0m", out)
			p.sendline(out)

			resend = False
			while True:
				res = p.readline()
				if res is None:
					time.sleep(0.1)
					continue
				elif res == "[ERROR] invalid checksum":
					logger.info("\x1B[31;1m< %s\x1B[0m", res)
					resend = True
					continue
				elif res == "[ERROR] invalid gcode":
					logger.info("\x1B[31;1m< %s\x1B[0m -> assuming it was a corruption", res)
					resend = True
					continue
				elif res == "[ERROR] too long extrusion prevented":
					logger.info("\x1B[31;1m< %s\x1B[0m -> assuming it was a corruption", res)
					resend = True
					continue
				elif res == "[ERROR] unknown command":
					logger.info("\x1B[31;1m< %s\x1B[0m -> assuming it was a corruption", res)
					resend = True
					continue
				elif re.match(r"\[ERROR\] gcode char invalid: '.' \([0-9A-F]{2}\)", res):
					logger.info("\x1B[31;1m< %s\x1B[0m", res)
					resend = True
					continue
				elif re.match(r"\[(ERROR)\].*", res):
					self._last_notices.append(res)
					logger.info("\x1B[31;1m< %s\x1B[0m", res)
					raise RuntimeError(res)
					continue
				elif re.match(r"\[(ECHO|VALUE)\].*", res):
					self._last_notices.append(res)
					logger.info("\x1B[32m< %s\x1B[0m", res)
					continue
				elif res == "ok":
					logger.info("\x1B[32m< %s\x1B[0m", res)
					break
				else:
					logger.info("\x1B[35;1m< %s\x1B[0m", res)
					continue

			if not resend:
				break

		return res


class SenderMarlin(object):

	def __init__(self, pipe=None, stdin=None, stdout=None):
		if pipe is None:
			self.pipe = pipe = Pipe(stdin=stdin, stdout=stdout, endline=b"\n")
		# Initialize
		self.verbose = verbose = True
		self._last_notices = collections.deque()

	def open(self, initial=True):
		p = self.pipe
		if initial:
			logger.info("Initializing TODO...")
			p.sendline("")
			p.sendline("")
			while True:
				res = p.readline()
				if res is None:
					break
				logger.info("\x1B[32m%s\x1B[0m", res)

	def close(self):
		p = self.pipe
		p.close()

	def queue(self, line):
		p = self.pipe

		def shorten(line):
			line = line.split(";")[0].rstrip()

			if line in (
			 "G21",
			 "G90",
			 "M82",
			 "M600", # Filament change
			 ):
				# Unsupported commands
				return
			if line.startswith("M117"):
				return line

			if not "*" in line:
				# Apply checksum
				s = ("%s " % line).encode("utf-8")
				cs = 0
				for v in bytearray(s):
					cs = cs ^ v
				cs = cs & 0xff
				return "%s *%d" % (line, cs)

		out = shorten(line)

		if out is None:
			return

		while True:
			logger.info("\x1B[33mNow sending %s (%s)\x1B[0m", out, line)
			p.sendline(out)

			resend = False
			while True:
				res = p.readline()
				if res is None:
					time.sleep(0.1)
					continue
				elif res.startswith("echo:"):
					self._last_notices.append(res)
					logger.info("\x1B[32m%s\x1B[0m", res)
					continue
				elif res == "ok":
					logger.info("\x1B[32m%s\x1B[0m", res)
					break
				else:
					logger.info("\x1B[35;1m“%s”\x1B[0m", res)
					continue

			if not resend:
				break

		return res



def main(args=None):

	if args is None:
		args = sys.argv[1:]

	import argparse

	parser = argparse.ArgumentParser(
	 description="g-code sender",
	)

	parser.add_argument("--log-level",
	 default="INFO",
	 help="Logging level (eg. INFO, see Python logging docs)",
	)

	parser.add_argument("--stdio-command",
	 help="Command to access g-code server",
	)

	parser.add_argument("--protocol",
	 help="protocol type",
	 choices=("grbl", "trinus", "marlin"),
	 default="grbl",
	)

	subparsers = parser.add_subparsers(
	 help='the command; type "%s COMMAND -h" for command-specific help' % sys.argv[0],
	 dest='command',
	)

	parser_send = subparsers.add_parser(
	 'send',
	 help="manage sending of g-code files to grbl",
	)

	parser_send.add_argument("--start-line",
	 help="line from which to start sending",
	 type=int,
	 default=1,
	)

	parser_send.add_argument("filename",
	 help="file to send",
	)

	try:
		import argcomplete
		argcomplete.autocomplete(parser)
	except:
		pass

	args = parser.parse_args(args)

	logging.basicConfig(
	 datefmt="%Y%m%dT%H%M%S",
	 level=getattr(logging, args.log_level),
	 format="%(asctime)-15s %(name)s %(levelname)s %(message)s"
	)

	with contextlib.ExitStack() as stack:
		if args.stdio_command is not None:
			cmd = shlex.split(args.stdio_command)
			proc = TerminatingPopen(cmd,
			 stdin=subprocess.PIPE,
			 stdout=subprocess.PIPE,
			)

			stack.enter_context(proc)

			stdin = proc.stdin
			stdout = proc.stdout
		else:
			stdin = sys.stdin.buffer
			stdout = sys.stdout.buffer


		if args.protocol == "trinus":
			sender = SenderTrinus(
			 stdin=stdin,
			 stdout=stdout,
			)
		elif args.protocol == "grbl":
			sender = SenderGrbl(
			 stdin=stdin,
			 stdout=stdout,
			)
		elif args.protocol == "marlin":
			sender = SenderMarlin(
			 stdin=stdin,
			 stdout=stdout,
			)

		if 0:
			pass

		elif args.command == "send":
			sender.open(initial=False)
			logger.info("Sending %s", args.filename)

			idx_line = 1
			try:
				with io.open(args.filename, "r") as f:
					for idx_line, line in enumerate(f):
						if idx_line+1 < args.start_line:
							continue
						line = line.rstrip()
						logger.info("Processing line % 4d (%s)", idx_line+1, line)
						if re.match(r".*\*\d+", line):
							""" Don't touch """
						else:
							if line.startswith("%"):
								continue
							if line.startswith("("):
								continue
							if line == "":
								continue
							line = line.split(";")[0].strip()
							if line == "":
								continue
							logger.info("Queueing line % 4d (%s)", idx_line+1, line)
						sender.queue(line)

			except KeyboardInterrupt:
				pass

			logger.info("Last line sent is %d", idx_line+1)

			if args.protocol == "grbl":
				idle_p = lambda x: x["state"] == "Idle"
				sender.wait_status(condition=idle_p)
			else:
				logger.info("\x1B[33mCaution, wait for remaining commands to be purged!\x1B[0m")


if __name__ == "__main__":
	ret = main()
	raise SystemExit(ret)
