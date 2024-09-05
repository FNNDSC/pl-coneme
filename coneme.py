#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

from chris_plugin import chris_plugin, PathMapper


import sys
import os
import numpy as np
import pdb
import scipy.io
from scipy import stats
import bct as bct
import pickle
import csv
import matplotlib.pyplot as plt
import copy

import pandas as pd


__version__ = "1.0.0"

DISPLAY_TITLE = r"""
       _
      | |
 _ __ | |______ ___ ___  _ __   ___ _ __ ___   ___
| '_ \| |______/ __/ _ \| '_ \ / _ \ '_ ` _ \ / _ \
| |_) | |     | (_| (_) | | | |  __/ | | | | |  __/
| .__/|_|      \___\___/|_| |_|\___|_| |_| |_|\___|
| |
|_|
"""


parser = ArgumentParser(
    description="""
A connectome csv file analyzer
                        """,
    formatter_class=ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "-p", "--pattern", default="**/*.csv", type=str, help="input file filter glob"
)
parser.add_argument(
    "--subj", default="", type=str, help="subject id (must appear in the file)"
)
parser.add_argument(
    "--atlas", default="", type=str, help="atlas name (must appear in the file)"
)
parser.add_argument(
    "--nnode", default="", type=str, help="number of nodes in connectome"
)
parser.add_argument(
    "--measurementfile",
    default="measures.txt",
    type=str,
    help="file with additional analysis meta",
)
parser.add_argument(
    "-V", "--version", action="version", version=f"%(prog)s {__version__}"
)


def csv_to_mat(csv_path):

    if os.path.exists(csv_path) == False:
        print("  ")
        print("++++++++ ERROR ++++++++")
        print("   %s does not exist. Cannot continue." % csv_path)
        print("+++++++++++++++++++++++")
        sys.exit(0)

    # convert csv to mat
    print("Reading in network from %s....." % csv_path)
    df = pd.read_csv(
        csv_path, header=None
    )  # <-do NOT read the first row as column names
    # convert the datafram in to a 2D numpy array, add to dict
    mat = df.to_numpy()

    return mat


def read_params(file):
    with open(file) as params_file:
        params = {}
        for iLine in params_file:
            if not (iLine[0] == "#") and not (iLine[0] == "\n"):
                values = iLine[0:-1].split("=")  # iLine[-1] = '\n'
                label = values[0]

                all_values = []
                for iValue in values[1].split(","):
                    try:
                        all_values.append(np.float64(iValue))  # integer
                    except:
                        # test if range was specified
                        val = iValue.strip()
                        if val[0] == "(":
                            val = val[1:-1].split(";")
                            val = np.arange(
                                np.float64(val[0]),
                                np.float64(val[2]) + np.float64(val[0]),
                                np.float64(val[1]),
                            )
                            all_values.extend(val)
                        else:
                            all_values.append(val)  # string

                if len(all_values) == 1:
                    all_values = all_values[0]
                params[label] = all_values

    return params


def get_standard_measures(mat, nNode):

    metrics = {}

    # Degree
    metrics["degree"] = bct.degrees_und(mat)

    # Density
    metrics["density"] = bct.density_und(mat)
    # Strength = sum of edge weights belonging to each node
    metrics["strength"] = bct.strengths_und(mat)

    # edge and nodal betweenness centrality (BC)
    wLen = wLen = bct.weight_conversion(mat, "lengths")
    eBCmat, nBC = bct.edge_betweenness_wei(wLen)
    # normalized:
    eBCmat = eBCmat / ((nNode - 1) * (nNode - 2))
    metrics["edge_BC_matrix"] = eBCmat
    nBC = nBC / ((nNode - 1) * (nNode - 2))
    metrics["node_BC"] = nBC

    # distance matrix & characteristic path length:
    [D, B] = bct.distance_wei(wLen)  # D = distance (shortest weighted path) matrix
    # B = number of edges in shortest weighted path matrix
    [lam, eff, ecc, rad, dia] = bct.charpath(D)  # Lam = CPL, eff = global efficiency,
    # ecc = eccentricity for each vertex, rad = radius, dia = diameter
    metrics["distance_matrix"] = D
    metrics["CPL"] = lam
    metrics["global_eff"] = eff

    # local efficiency
    eLoc = bct.efficiency_wei(mat, True)
    metrics["local_eff"] = eLoc

    # clustering coefficient
    metrics["node_CC"] = bct.clustering_coef_wu(mat)

    # transitivity - ratio of triangles to triplets
    # note: bct.transitivity_wu takes only weightes btw 0 and 1.
    metrics["node_transitivity"] = bct.transitivity_wu(mat)
    W_nrm = bct.weight_conversion(mat, "normalize")
    metrics["node_transitivity_normMat"] = bct.transitivity_wu(W_nrm)

    return metrics


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title="Coneme",
    category="",  # ref. https://chrisstore.co/plugins
    min_memory_limit="100Mi",  # supported units: Mi, Gi
    min_cpu_limit="1000m",  # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0,  # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """

    print(DISPLAY_TITLE)

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    mapper = PathMapper.file_mapper(
        inputdir, outputdir, glob=options.pattern, suffix=".pickle"
    )
    for input_file, output_file in mapper:
        # The code block below is a small and easy example of how to use a ``PathMapper``.
        # It is recommended that you put your functionality in a helper function, so that
        # it is more legible and can be unit tested.
        nw = csv_to_mat(input_file)
        measureFile: Path = inputdir / options.measurementfile
        params = read_params(measureFile)

        if params["flag_standard_measures"] == 1:
            print(
                f"""Computing standard measures for subject {options.subj}, with atlas {options.atlas}...
            """
            )
            output = get_standard_measures(nw, nw.shape[0])

        with open(output_file, "wb") as output_file:
            pickle.dump(output, output_file, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    main()
