#!/usr/bin/env python
# -*- coding: utf-8 vi:noet
# 2022-05-06 - Convert STL to OpenSCAD

import io, subprocess, sys, os
import logging

# FIXME - I have an euclid3 symlink to euclid
sys.path.append(os.path.dirname(__file__))

import solid


logger = logging.getLogger()


def main(args=None):

	if args is None:
		args = sys.argv[1:]

	import argparse

	parser = argparse.ArgumentParser(
	 description="Convert STL to SCAD (via import statement); output file is next to input",
	)

	parser.add_argument("--log-level",
	 default="INFO",
	 help="Logging level (eg. INFO, see Python logging docs)",
	)

	parser.add_argument("path")


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

	dirname, basename = os.path.split(os.path.abspath(args.path))
	os.chdir(dirname)
	stl_fn = basename

	model = solid.import_stl(stl_fn)

	try:
		import camvtk
		stl = camvtk.STLSurf(stl_fn)
		polydata = stl.src.GetOutput()
		model_bounds = polydata.GetBounds()
		minx, maxx, miny, maxy, minz, maxz = model_bounds
		spanx = maxx-minx
		spany = maxy-miny
		spanz = maxz-minz
		logger.info("X span: %s (%s-%s)", spanx, minx, maxx)
		logger.info("Y span: %s (%s-%s)", spany, miny, maxy)
		logger.info("Z span: %s (%s-%s)", spanz, minz, maxz)
	except:
		pass

	solid.scad_render_to_file(model, stl_fn + ".scad")


if __name__ == "__main__":
	ret = main()
	raise SystemExit(ret)

