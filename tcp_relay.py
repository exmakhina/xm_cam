#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# SPDX-FileCopyrightText: 2016,2022 Jérôme Carretero <cJ@zougloub.eu> & contributors
# SPDX-License-Identifier: MIT
# Proxy to allow a client (maybe more) to connect by TCP to a gcode server

"""
This provides a local interface to a remote gcode server.
Multiple connections to it are allowed (which may be dangerous).
"""

import socket, select, time, sys, collections, io, os, subprocess
import contextlib
import logging
import fcntl
import shlex


logger = logging.getLogger()


class TerminatingPopen(subprocess.Popen):
	"""
	Like subprocess.Popen but ensures the subprocess is terminated
	when __exit__ is called.
	"""
	def __init__(self, cmd, **kw):
		if os.name == "nt":
			kw.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
		super().__init__(cmd, **kw)

	def __exit__(self, *args):
		if os.name == "nt":
			self.terminate()
			os.kill(self.pid, signal.CTRL_BREAK_EVENT)
		else:
			super().__exit__(*args)


def main(argv=None):
	import argparse

	parser = argparse.ArgumentParser(
	 description="TCP listener multiplexing gcode server",
	)

	parser.add_argument("--log-level",
	 default="INFO",
	 help="Logging level (eg. INFO, see Python logging docs)",
	)

	parser.add_argument("stdio_command",
	 help="Command to run to get stdio",
	)


	try:
		import argcomplete
		argcomplete.autocomplete(parser)
	except:
		pass

	args = parser.parse_args(argv)

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

		for fd in (stdin, stdout):
			flag = fcntl.fcntl(fd, fcntl.F_GETFL)
			fcntl.fcntl(fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)
			flag = fcntl.fcntl(fd, fcntl.F_GETFL)
			if flag & os.O_NONBLOCK == 0:
				raise RuntimeError(f"Couldn't put {fd} as non-blocking")

		channel = []

		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		server.bind(("127.0.0.1", 9999))
		server.listen(5)

		timeout = 1

		try:
			while True:
				rs = [server, stdout] + channel
				ws = []
				xs = []
				rs, ws, xs = select.select(rs, ws, xs, timeout)
				logger.debug("rs=%s ws=%s xs=%s", rs, ws, xs)
				for r in rs:
					if r is server:
						clientsock, clientaddr = r.accept()
						channel.append(clientsock)
						break

					elif r is stdout:
						data = r.read(4096)
						name = "[{}]".format("gcode".center(4*3+3+1+5))
						sys.stdout.write(f"\x1B[32;1m{name}\x1B[0m {data.decode('utf-8')}")
						sys.stdout.flush()
						if not data:
							logger.info("gcode server has disconnected")
							for peer in channel:
								peer.close()
							return
						for peer in channel:
							peer.send(data)

					elif r in channel:
						data = r.recv(4096)
						host, port = r.getpeername()
						name = "[{}]".format(f"{host}:{port}".center(4*3+3+1+5))
						sys.stdout.write(f"\x1B[33;1m{name}\x1B[0m {data.decode('utf-8')}")
						sys.stdout.flush()
						if data:
							stdin.write(data)
							stdin.flush()
						else:
							logger.info("%s has disconnected", r.getpeername())
							r.close()
							channel.remove(r)
		except KeyboardInterrupt:
			logger.info("Bye")


if __name__ == "__main__":
	ret = main()
	raise SystemExit(ret)
