#!/bin/env python3
# -*- coding: utf-8 -*-
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#    A copy of the GNU General Public License is available at
#    http://www.gnu.org/licenses/gpl-3.0.html

"""Perform assembly based on debruijn graph."""

import argparse
import os
import sys
from pathlib import Path
import networkx as nx
from networkx import DiGraph, all_simple_paths, lowest_common_ancestor, has_path, random_layout, draw, spring_layout
import matplotlib
from operator import itemgetter
import random
random.seed(9001)
from random import randint
import statistics
import textwrap
import matplotlib.pyplot as plt
from typing import Iterator, Dict, List
matplotlib.use("Agg")

__author__ = "Manel Benkortebi"
__copyright__ = "Universite Paris Diderot"
__credits__ = ["Manel Benkortebi"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Manel Benkortebi"
__email__ = "manel.benkortebi@etu.u-paris.fr"
__status__ = "Developpement"

def isfile(path: str) -> Path:  # pragma: no cover
    """Check if path is an existing file.

    :param path: (str) Path to the file

    :raises ArgumentTypeError: If file does not exist

    :return: (Path) Path object of the input file
    """
    myfile = Path(path)
    if not myfile.is_file():
        if myfile.is_dir():
            msg = f"{myfile.name} is a directory."
        else:
            msg = f"{myfile.name} does not exist."
        raise argparse.ArgumentTypeError(msg)
    return myfile


def get_arguments(): # pragma: no cover
    """Retrieves the arguments of the program.

    :return: An object that contains the arguments
    """
    # Parsing arguments
    parser = argparse.ArgumentParser(description=__doc__, usage=
                                     "{0} -h"
                                     .format(sys.argv[0]))
    parser.add_argument('-i', dest='fastq_file', type=isfile,
                        required=True, help="Fastq file")
    parser.add_argument('-k', dest='kmer_size', type=int,
                        default=22, help="k-mer size (default 22)")
    parser.add_argument('-o', dest='output_file', type=Path,
                        default=Path(os.curdir + os.sep + "contigs.fasta"),
                        help="Output contigs in fasta file (default contigs.fasta)")
    parser.add_argument('-f', dest='graphimg_file', type=Path,
                        help="Save graph as an image (png)")
    return parser.parse_args()


def read_fastq(fastq_file: Path) -> Iterator[str]:
    """Extract reads from fastq files.

    :param fastq_file: (Path) Path to the fastq file.
    :return: A generator object that iterate the read sequences. 
    """
    with open(fastq_file,'r') as fastq:
        for line in fastq:
            yield(next(fastq).strip())
            next(fastq)
            next(fastq)


def cut_kmer(read: str, kmer_size: int) -> Iterator[str]:
    """Cut read into kmers of size kmer_size.
    
    :param read: (str) Sequence of a read.
    :param kmer_size: (int) Length of the k-mers.
    :return: A generator object that provides the k-mers (str) of size kmer_size.
    """
    for i in range(len(read) - kmer_size + 1):
        kmer = read[i:i + kmer_size]
        yield kmer



def build_kmer_dict(fastq_file: Path, kmer_size: int) -> Dict[str, int]:
    """Build a dictionary of all k-mer occurrences in the FASTQ file.

    :param fastq_file: (Path) Path to the FASTQ file.
    :param kmer_size: (int) Length of the k-mers.
    :return: A dictionary with k-mers as keys and their occurrences as values.
    """
    kmer_counts = {}

    for sequence in read_fastq(fastq_file):
        for kmer in cut_kmer(sequence, kmer_size):
            kmer_counts[kmer] = kmer_counts.get(kmer, 0) + 1

    return kmer_counts


def build_graph(kmer_dict: Dict[str, int]) -> nx.DiGraph:
    """Build a directed and weighted graph representing k-mer prefixes and suffixes.

    :param kmer_dict: A dictionary with k-mers as keys and their occurrences as values.
    :return: A NetworkX DiGraph representing the k-mer graph.
    """
    graph = nx.DiGraph()

    for kmer, count in kmer_dict.items():
        prefix = kmer[:-1]
        suffix = kmer[1:]

        if not graph.has_node(prefix):
            graph.add_node(prefix)
        if not graph.has_node(suffix):
            graph.add_node(suffix)
        if graph.has_edge(prefix, suffix):
            graph[prefix][suffix]['weight'] += count
        else:
            graph.add_edge(prefix, suffix, weight=count)

    return graph

def remove_paths(graph: DiGraph, path_list: List[List[str]],
delete_entry_node: bool, delete_sink_node: bool) -> DiGraph:
    """Remove a list of path in a graph. A path is set of connected node in
    the graph

    :param graph: (nx.DiGraph) A directed graph object
    :param path_list: (list) A list of path
    :param delete_entry_node: (boolean) True->We remove the first node of a path 
    :param delete_sink_node: (boolean) True->We remove the last node of a path
    :return: (nx.DiGraph) A directed graph object
    """
    modified_graph = graph.copy()

    for path in path_list:
        if delete_entry_node and delete_sink_node:
            modified_graph.remove_nodes_from(path)
        elif delete_entry_node and not delete_sink_node:
            modified_graph.remove_nodes_from(path[:-1])
        elif  not delete_entry_node and delete_sink_node:
            modified_graph.remove_nodes_from(path[1:])
        elif not delete_entry_node and not delete_sink_node:
            modified_graph.remove_nodes_from(path[1:-1])

    return modified_graph


def select_best_path(graph: DiGraph, path_list: List[List[str]],
path_length: List[int], weight_avg_list: List[float],
delete_entry_node: bool=False, delete_sink_node: bool=False) -> DiGraph:
    """Select the best path between different paths

    :param graph: (nx.DiGraph) A directed graph object
    :param path_list: (list) A list of path
    :param path_length_list: (list) A list of length of each path
    :param weight_avg_list: (list) A list of average weight of each path
    :param delete_entry_node: (boolean) True->We the first node of a path 
    :param delete_sink_node: (boolean) True->We remove the last node of a path
    :return: (nx.DiGraph) A directed graph object
    """
    weight_stddev = statistics.stdev(weight_avg_list)
    length_stddev = statistics.stdev(path_length)
    path_index = None

    if weight_stddev > 0:
        path_index = weight_avg_list.index(max(weight_avg_list))
    elif length_stddev > 0:
        path_index = path_length.index(max(path_length))
    else:
        path_index = random.randint(0, len(path_length) - 1)

    path_list.pop(path_index)
    modified_graph = graph.copy()

    modified_graph = remove_paths(graph, path_list , delete_entry_node, delete_sink_node)

    return modified_graph



def path_average_weight(graph: DiGraph, path: List[str]) -> float:
    """Compute the weight of a path

    :param graph: (nx.DiGraph) A directed graph object
    :param path: (list) A path consist of a list of nodes
    :return: (float) The average weight of a path
    """
    return statistics.mean([d["weight"] for (u, v, d) in graph.subgraph(path).edges(data=True)])


def solve_bubble(graph: DiGraph, ancestor_node: str, descendant_node: str) -> DiGraph:
    """Explore and solve bubble issue

    :param graph: (nx.DiGraph) A directed graph object
    :param ancestor_node: (str) An upstream node in the graph 
    :param descendant_node: (str) A downstream node in the graph
    :return: (nx.DiGraph) A directed graph object
    """
    paths = list(nx.all_simple_paths(graph, ancestor_node, descendant_node))
    path_length = [len(i) for i in paths]
    path_weights = [path_average_weight(graph, path) for path in paths]

    selected_graph = select_best_path(graph, paths, path_length, path_weights)
    return selected_graph

def simplify_bubbles(graph: DiGraph) -> DiGraph:
    """Detect and explode bubbles
    
    :param graph: (nx.DiGraph) A directed graph object
    :return: (nx.DiGraph) A directed graph object
    """
    bubble = False
    for node in graph.nodes:
        predecessors = list(graph.predecessors(node))

        if len(predecessors) > 1:
            for i in range(len(predecessors)):
                for j in range(i + 1, len(predecessors)):
                    ancestor_node = nx.lowest_common_ancestor(graph,
                    predecessors[i], predecessors[j])

                    if ancestor_node is not None:
                        bubble = True
                        break

        if bubble:
            break

    if bubble:
        ancestor = ancestor_node
        node = node
        graph = solve_bubble(graph, ancestor, node)
        return simplify_bubbles(graph)

    return graph


def solve_entry_tips(graph: DiGraph, starting_nodes: List[str]) -> DiGraph:
    """Remove entry tips

    :param graph: (nx.DiGraph) A directed graph object
    :param starting_nodes: (list) A list of starting nodes
    :return: (nx.DiGraph) A directed graph object
    """
    for node in graph.nodes:
        all_paths = []
        path_length=[]
        path_weights=[]
        if len(list(graph.predecessors(node))) > 1:
            for starting_node in starting_nodes:
                if node not in starting_nodes:
                    paths = list(nx.all_simple_paths(graph, starting_node, node))
                    all_paths.append(paths[0])
            if len(all_paths) > 1:
                for i, path in enumerate(all_paths):
                    path_length.append(len(path))
                    if path_length[i] > 1 :
                        path_weights.append(path_average_weight(graph, all_paths[i]))
                    else:
                        path_weights.append([all_paths[i][0]][all_paths[i][1]]["weight"])
                graph = solve_entry_tips(select_best_path(
                    graph, all_paths, path_length, path_weights,
                    delete_entry_node=True, delete_sink_node=False), starting_nodes)
                break
    return graph

def solve_out_tips(graph: DiGraph, ending_nodes: List[str]) -> DiGraph:
    """Remove out tips

    :param graph: (nx.DiGraph) A directed graph object
    :param ending_nodes: (list) A list of ending nodes
    :return: (nx.DiGraph) A directed graph object
    """
    for node in graph.nodes:
        all_paths = []
        path_length=[]
        path_weights=[]
        if len(list(graph.successors(node))) > 1:
            for ending_node in ending_nodes:
                if node not in ending_nodes:
                    paths = list(nx.all_simple_paths(graph, node,ending_node))
                    all_paths.append(paths[0])
            if len(all_paths) > 1:
                for i, path in enumerate(all_paths):
                    path_length.append(len(path))
                    if path_length[i] > 1 :
                        path_weights.append(path_average_weight(graph, all_paths[i]))
                    else:
                        path_weights.append([all_paths[i][0]][all_paths[i][1]]["weight"])
                graph = solve_out_tips(select_best_path(
                    graph, all_paths, path_length, path_weights,
                    delete_entry_node=False, delete_sink_node=True), ending_nodes)
                break
    return graph

def get_starting_nodes(graph: DiGraph) -> List[str]:
    """Get nodes without predecessors

    :param graph: (nx.DiGraph) A directed graph object
    :return: (list) A list of all nodes without predecessors
    """
    starting_nodes = [node for node in graph.nodes() if not any(graph.predecessors(node))]
    return starting_nodes


def get_sink_nodes(graph: DiGraph) -> List[str]:
    """Get nodes without successors

    :param graph: (nx.DiGraph) A directed graph object
    :return: (list) A list of all nodes without successors
    """
    ending_nodes = [node for node in graph.nodes() if not any(graph.successors(node))]
    return ending_nodes


def get_contigs(graph: DiGraph, starting_nodes: List[str],
ending_nodes: List[str]) -> List[tuple[str, int]]:
    """Extract the contigs from the graph

    :param graph: (nx.DiGraph) A directed graph object
    :param starting_nodes: (list) A list of nodes without predecessors
    :param ending_nodes: (list) A list of nodes without successors
    :return: (list) List of [contiguous sequence and their length]
    """
    contigs = []

    for start_node in starting_nodes:
        for end_node in ending_nodes:
            if nx.has_path(graph, start_node, end_node):
                paths = list(nx.all_simple_paths(graph, start_node, end_node))
                contig = paths[0][0]
                for path in paths[0][1:]:
                    contig += path[-1]
            contig_length = len(contig)
            contigs.append((contig, contig_length))
    return contigs


def save_contigs(contigs_list: List[tuple[str, int]], output_file: Path) -> None:
    """Write all contigs in FASTA format.

    :param contigs_list: List of (contig, contig length).
    :param output_file: Path to the output file.
    """
    with open(output_file, 'w') as file:
        for i, (contig, length) in enumerate(contigs_list):
            file.write(f'>contig_{i} len={length}\n')
            wrapped_contig = textwrap.fill(contig, width=80)
            file.write(wrapped_contig)
            file.write('\n')


def draw_graph(graph: DiGraph, graphimg_file: Path) -> None: # pragma: no cover
    """Draw the graph

    :param graph: (nx.DiGraph) A directed graph object
    :param graphimg_file: (Path) Path to the output file
    """
    fig, ax = plt.subplots()
    elarge = [(u, v) for (u, v, d) in graph.edges(data=True) if d['weight'] > 3]
    #print(elarge)
    esmall = [(u, v) for (u, v, d) in graph.edges(data=True) if d['weight'] <= 3]
    #print(elarge)
    # Draw the graph with networkx
    #pos=nx.spring_layout(graph)
    pos = nx.random_layout(graph)
    nx.draw_networkx_nodes(graph, pos, node_size=6)
    nx.draw_networkx_edges(graph, pos, edgelist=elarge, width=6)
    nx.draw_networkx_edges(graph, pos, edgelist=esmall, width=6, alpha=0.5,
    edge_color='b', style='dashed')
    #nx.draw_networkx(graph, pos, node_size=10, with_labels=False)
    # save image
    plt.savefig(graphimg_file.resolve())


#==============================================================
# Main program
#==============================================================
def main() -> None: # pragma: no cover
    """
    Main program function
    """
    # Get arguments
    args = get_arguments()
    kmer_dict = build_kmer_dict(args.fastq_file, args.kmer_size)
    graph = build_graph(kmer_dict)
    graph = simplify_bubbles(graph)
    graph = solve_entry_tips(graph, get_starting_nodes(graph))
    graph = solve_out_tips(graph, get_sink_nodes(graph))
    contigs = get_contigs(graph, get_starting_nodes(graph), get_sink_nodes(graph))
    save_contigs(contigs, args.output_file)
    # Fonctions de dessin du graphe
    # A decommenter si vous souhaitez visualiser un petit
    # graphe
    # Plot the graph
    if args.graphimg_file:
        draw_graph(graph, args.graphimg_file)


if __name__ == '__main__': # pragma: no cover
    main()
