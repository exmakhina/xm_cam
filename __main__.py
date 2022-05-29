#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# CAM utilities CLI
# SPDX-FileCopyrightText: 2022 Jérôme Carretero <cJ@zougloub.eu>
# SPDX-License-Identifier: MIT

import sys
import logging


def main(args=None):

	if args is None:
		args = sys.argv[1:]

	import argparse

	parser = argparse.ArgumentParser(
	 description="CAM CLI",
	)

	parser.add_argument("--log-level",
	 default="INFO",
	 help="Logging level (eg. INFO, see Python logging docs)",
	)

	subparsers = parser.add_subparsers(
	 help='the command; type "%s COMMAND -h" for command-specific help' % sys.argv[0],
	 dest='command',
	)


	subp = subparsers.add_parser(
	 "stl2scad",
	 help="Run stl2scad",
	)

	subp.add_argument("rest",
	 nargs=argparse.REMAINDER,
	)

	def do_stl2scad(args):
		from .stl2scad import main
		return main(args.rest)

	subp.set_defaults(func=do_stl2scad)


	subp = subparsers.add_parser(
	 "meshconv",
	 help="Run meshconv",
	)

	subp.add_argument("src",
	)

	subp.add_argument("dst",
	)

	def do_meshconv(args):
		import os
		import subprocess

		cmd = [
		 os.path.join(os.path.dirname(__file__), "meshconv"),
		 args.src,
		 args.dst,
		]
		subprocess.run(cmd, check=True)

	subp.set_defaults(func=do_meshconv)


	subp = subparsers.add_parser(
	 "gcode_proxy",
	 help="Run gcode proxy",
	)

	def do_gcode_proxy(args):
		from .gcode_proxy import main
		return main(rest)

	subp.set_defaults(func=do_gcode_proxy)


	subp = subparsers.add_parser(
	 "gcode_sender",
	 help="Run gcode sender",
	)

	def do_gcode_sender(args):
		from .gcode_sender import main
		return main(rest)

	subp.set_defaults(func=do_gcode_sender)


	try:
		import argcomplete
		argcomplete.autocomplete(parser)
	except:
		pass

	args, rest = parser.parse_known_args(args)

	logging.basicConfig(
	 datefmt="%Y%m%dT%H%M%S",
	 level=getattr(logging, args.log_level),
	 format="%(asctime)-15s %(name)s %(levelname)s %(message)s"
	)

	if getattr(args, 'func', None) is None:
		parser.print_help()
		return 1
	else:
		return args.func(args)

if __name__ == "__main__":
	ret = main()
	raise SystemExit(ret)
