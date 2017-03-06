#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# PYTHON_ARGCOMPLETE_OK
# g-code sender

import socket, io, re, time, sys, binascii, collections


class Pipe(object):
	"""
	TCP connector
	"""
	def __init__(self, host=None, port=None, endline=b"\n"):
		self.s = s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.verbose = False
		self.host = host or "localhost"
		self.port = port or 9999
		self._endline = endline

	def open(self):
		s = self.s
		s.connect((self.host, self.port))
		s.settimeout(2.0)

	def close(self):
		s = self.s
		s.close()

	def readline(self, timeout=None):
		s = self.s
		buf = io.BytesIO()
		while True:
			if self.verbose:
				print("Reading")
			try:
				data = s.recv(180, socket.MSG_PEEK)
			except socket.timeout as e:
				return None
			except socket.error as e:
				print("Exception %s" % e)
				time.sleep(0.1)
				continue
			if self.verbose:
				print("Read %d: %s" % (len(data), binascii.hexlify(data)))
			for i in range(len(data)):
				if data[i] == b"\n":
					discard = i+1
					if self.verbose:
						print("Discarding %d: %s" % (discard, binascii.hexlify(data[:discard])))
					trash = s.recv(discard)
					if self.verbose:
						print("Discarded %s" % (binascii.hexlify(trash)))

						if self.verbose:
							print("Returning!")
					try:
						if self._endline == b"\r\n":
							end = -1
						else:
							end = None
						return buf.getvalue()[:end].decode()
					except UnicodeDecodeError:
						return "???"
				if self.verbose:
					print("Adding %s" % (data[i]))
				buf.write(data[i])

			trash = s.recv(len(data))
			if self.verbose:
				print("Discarded %s" % (binascii.hexlify(trash)))

	def sendline(self, l):
		s = self.s
		s.send(("%s\r\n" % l).encode())


class SenderGrbl(object):
	queue_full_retry = 0.3

	def __init__(self, pipe=None, host=None, port=None):
		if pipe is None:
			self.pipe = pipe = Pipe(host=host, port=port, endline=b"\r\n")
		# Initialize
		self.verbose = verbose = True

	def open(self, initial=True):
		p = self.pipe
		p.open()
		if initial:
			print("Initializing grbl...")
			p.sendline("")
			p.sendline("")
			while True:
				res = p.readline()
				if res is None:
					break
				print("\x1B[32m%s\x1B[0m" % res)

	def close(self):
		p = self.pipe
		p.close()

	def queue(self, line):
		p = self.pipe

		if line != "?":
			can_send = lambda x: x["cmdbuf"] < 10 and x["rxbuf"] < 100
			self.wait_status(condition=can_send, poll_delay=self.queue_full_retry)

		print("\x1B[33mNow sending %s\x1B[0m" % line)
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
				print("\x1B[32m%s\x1B[0m" % res)
				continue
			if re.match(r"<.*>", res):
				self.last_status = res
				print("\x1B[32m%s\x1B[0m" % res)
				continue
			break

		print("\x1B[32m%s\x1B[0m" % res)
		assert res == "ok", res

		if line == "M2":
			"""
			grbl outputs extra info when M2 is said
			"""
			print("\x1B[31mM2\x1B[0m")
			x = p.readline()
			print("\x1B[32m%s\x1B[0m" % x)
			x = p.readline()
			print("\x1B[32m%s\x1B[0m" % x)
			x = p.readline()
			print("\x1B[32m%s\x1B[0m" % x)
			x = p.readline()
			print("\x1B[32m%s\x1B[0m" % x)

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
				print("\x1B[32m%s\x1B[0m" % res)
				continue
			if re.match(r"<.*>", res):
				self.last_status = res
				print("\x1B[32m%s\x1B[0m" % res)
				continue

		m = re.match(r"<(?P<state>\S+),MPos:(?P<mpos>\S+),WPos:(?P<wpos>\S+),Buf:(?P<cmdbuf>\S+),RX:(?P<rxbuf>\S+),Ln:(?P<ln>\S+),F:(?P<feed>\S+)\.>", self.last_status)
		assert m is not None

		res = dict(
		 state=m.group("state"),
		 cmdbuf=int(m.group("cmdbuf")),
		 rxbuf=int(m.group("rxbuf")),
		)

		return res

	def close(self):
		p = self.pipe
		p.close()


class SenderTrinus(object):

	def __init__(self, pipe=None, host=None, port=None):
		if pipe is None:
			self.pipe = pipe = Pipe(host=host, port=port, endline=b"\n")
		# Initialize
		self.verbose = verbose = True
		self._last_notices = collections.deque()

	def open(self, initial=True):
		p = self.pipe
		p.open()
		if initial:
			print("Initializing TODO...")
			p.sendline("")
			p.sendline("")
			while True:
				res = p.readline()
				if res is None:
					break
				print("\x1B[32m%s\x1B[0m" % res)

	def close(self):
		p = self.pipe
		p.close()

	def queue(self, line):
		p = self.pipe

		def shorten(line):
			line = line.split(";")[0].rstrip()
			if line.startswith("M117"):
				return line

			# Apply checksum
			s = ("%s " % line).encode("utf-8")
			cs = 0
			for v in bytearray(s):
				cs = cs ^ v
			cs = cs & 0xff
			return "%s *%d" % (line, cs)

		out = shorten(line)

		while True:
			print("\x1B[33mNow sending %s (%s)\x1B[0m" % (out, line))
			p.sendline(out)

			resend = False
			while True:
				res = p.readline()
				if res is None:
					time.sleep(0.1)
					continue
				elif res == "[ERROR] invalid checksum":
					print("\x1B[31;1m%s\x1B[0m" % res)
					resend = True
					continue
				elif re.match(r"\[(ERROR)\].*", res):
					self._last_notices.append(res)
					print("\x1B[31;1m%s\x1B[0m" % res)
					raise RuntimeError(res)
					continue
				elif re.match(r"\[(ECHO|VALUE)\].*", res):
					self._last_notices.append(res)
					print("\x1B[32m%s\x1B[0m" % res)
					continue
				elif res == "ok":
					print("\x1B[32m%s\x1B[0m" % res)
					break
				else:
					print("\x1B[35;1m%s\x1B[0m" % res)
					continue

			if not resend:
				break

		return res

	def close(self):
		p = self.pipe
		p.close()


if __name__ == '__main__':

	import argparse

	parser = argparse.ArgumentParser(
	 description="g-code sender",
	)

	parser.add_argument("--host",
	 help="hostname for TCP/IP connection to GRBL bridge",
	 default="localhost",
	)

	parser.add_argument("--port",
	 help="port number for TCP/IP connection to GRBL bridge",
	 default=9999,
	 type=int,
	)

	parser.add_argument("--protocol",
	 help="protocol type",
	 choices=("grbl", "trinus"),
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

	parser_send.add_argument("filename",
	 help="file to send",
	)

	try:
		import argcomplete
		argcomplete.autocomplete(parser)
	except:
		pass

	args = parser.parse_args()

	if args.protocol == "trinus":
		sender = SenderTrinus(
		 host=args.host,
		 port=args.port,
		)
	elif args.protocol == "grbl":
		sender = SenderGrbl(
		 host=args.host,
		 port=args.port,
		)

	if 0:
		pass

	elif args.command == "send":
		sender.open(initial=False)
		print("Sending %s" % args.filename)

		idx_line = 1
		try:
			with io.open(args.filename, "r") as f:
				for idx_line, line in enumerate(f):
					if re.match(r".*\*\d+", line):
						""" Don't touch """
					else:
						line = line.rstrip()
						if line.startswith("%"):
							continue
						if line.startswith("("):
							continue
						line = line.split(";")[0]
						print("Sending line % 4d" % (idx_line+1))
					sender.queue(line)
					idx_line += 1
		except KeyboardInterrupt:
			pass

		print("Last line sent is %d" % idx_line)

		if args.protocol == "grbl":
			idle_p = lambda x: x["state"] == "Idle"
			sender.wait_status(condition=idle_p)
		else:
			print("\x1B[33mCaution, wait for remaining commands to be purged!\x1B[0m")

		sender.close()

		if 0:
			p = Pipe()
			p.open()
			p.sendline("?")
			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)
			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)
			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)
			p.sendline("?")
			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)

			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)

			time.sleep(1)
			p.sendline("?")
			res = p.readline()
			print("\x1B[32m%s\x1B[0m" % res)

			p.close()

