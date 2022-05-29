// Mesh converter using CGAL
// SPDX-FileCopyrightText: 2016,2022 Jérôme Carretero <cJ@zougloub.eu> & contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/IO/polygon_mesh_io.h>
#include <fstream>
#include <iostream>

typedef CGAL::Exact_predicates_inexact_constructions_kernel   K;
using FT       = typename K::FT;
using Vector_3 = typename K::Vector_3;
typedef CGAL::Surface_mesh<K::Point_3>                        Mesh;

namespace PMP = CGAL::Polygon_mesh_processing;
namespace params = PMP::parameters;

int main(int argc, char* argv[])
{
	const std::string src(argv[1]);
	const std::string dst(argv[2]);

	Mesh mesh;

	if(!PMP::IO::read_polygon_mesh(src, mesh)) {
		std::cerr << "Invalid input." << std::endl;
		return 1;
	}

	CGAL::IO::write_polygon_mesh(dst, mesh, CGAL::parameters::stream_precision(17));
	return 0;
}
