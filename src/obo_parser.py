#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
Created on Feb 23, 2010

@author: brentp

This file was adopted from a GitHub repo called 'goatools':
https://github.com/tanghaibao/goatools/blob/master/goatools/obo_parser.py
"""

import os
import sys
import logging
from exceptions import EOFError
from hierarchy import Hierarchy

typedef_tag, term_tag = "[Typedef]", "[Term]"


def after_colon(line):
    # macro for getting anything after the :
    return line.split(":", 1)[1].strip()


def read_until(handle, start):
    # read each line until it has a certain start, and then puts
    # the start tag back
    while 1:
        pos = handle.tell()
        line = handle.readline()
        if not line:
            break
        if line.startswith(start):
            handle.seek(pos)
            return
    raise EOFError("%s tag cannot be found" % start)


class OBOReader:
    """
    parse obo file, usually the most updated can be downloaded from
    http://www.geneontology.org/ontology/obo_format_1_2/gene_ontology.1_2.obo
    """

    def __init__(self, obo_file="gene_ontology.1_2.obo"):

        if not os.path.exists(obo_file):
            logging.error("Download obo file first and save as: %s" % obo_file)
            sys.exit(1)
        self._handle = file(obo_file)

    def __iter__(self):

        line = self._handle.readline()
        if not line.startswith(term_tag):
            read_until(self._handle, term_tag)
        while 1:
            yield self.next()

    def next(self):

        lines = []
        line = self._handle.readline()
        if not line or line.startswith(typedef_tag):
            raise StopIteration

        # read until the next tag and save everything in between
        while 1:
            pos = self._handle.tell()   # save current postion for roll-back
            line = self._handle.readline()
            if not line or (line.startswith(typedef_tag)
                            or line.startswith(term_tag)):
                self._handle.seek(pos)  # roll-back
                break
            lines.append(line)

        rec = GOTerm()
        for line in lines:
            if line.startswith("id:"):
                rec.id = after_colon(line)
            if line.startswith("alt_id:"):
                rec.alt_ids.append(after_colon(line))
            elif line.startswith("name:"):
                rec.name = after_colon(line)
            elif line.startswith("namespace:"):
                rec.namespace = after_colon(line)
            elif line.startswith("is_a:"):
                rec._parents.append(after_colon(line).split()[0])
            elif (line.startswith("is_obsolete:") and
                  after_colon(line) == "true"):
                rec.is_obsolete = True

        return rec


class GOTerm:
    """
    GO term, actually contain a lot more properties than interfaced here
    """

    def __init__(self):
        self.id = ""                # GO:xxxxxx
        self.name = ""              # description
        self.namespace = ""         # BP, CC, MF
        self._parents = []          # is_a basestring of parents
        self.parents = []           # parent records
        self.children = []          # children records
        self.level = -1             # distance from root node
        self.is_obsolete = False    # is_obsolete
        self.alt_ids = []           # alternative identifiers

    def __str__(self):
        obsolete = "obsolete" if self.is_obsolete else ""
        return "%s\tlevel-%02d\t%s [%s] %s" % (self.id, self.level, self.name,
                                               self.namespace, obsolete)

    def __repr__(self):
        return "GOTerm('%s')" % (self.id)

    def has_parent(self, term):
        for p in self.parents:
            if p.id == term or p.has_parent(term):
                return True
        return False

    def has_child(self, term):
        for p in self.children:
            if p.id == term or p.has_child(term):
                return True
        return False

    def get_all_parents(self):
        all_parents = set()
        for p in self.parents:
            all_parents.add(p.id)
            all_parents |= p.get_all_parents()
        return all_parents

    def get_all_children(self):
        all_children = set()
        for p in self.children:
            all_children.add(p.id)
            all_children |= p.get_all_children()
        return all_children

    def get_all_parent_edges(self):
        all_parent_edges = set()
        for p in self.parents:
            all_parent_edges.add((self.id, p.id))
            all_parent_edges |= p.get_all_parent_edges()
        return all_parent_edges

    def get_all_child_edges(self):
        all_child_edges = set()
        for p in self.children:
            all_child_edges.add((p.id, self.id))
            all_child_edges |= p.get_all_child_edges()
        return all_child_edges


class GODag(dict):

    def __init__(self, obo_file="gene_ontology.1_2.obo"):

        self.load_obo_file(obo_file)

    def load_obo_file(self, obo_file):

        logging.info('Loading OBO file %s' % obo_file)
        obo_reader = OBOReader(obo_file)
        for rec in obo_reader:
            self[rec.id] = rec
            for alt in rec.alt_ids:
                self[alt] = rec

        self.populate_terms()
        logging.info('%d nodes imported from OBO file' % len(self))

    def populate_terms(self):

        def depth(rec):
            if rec.level < 0:
                if not rec.parents:
                    rec.level = 0
                else:
                    rec.level = min(depth(rec) for rec in rec.parents) + 1
            return rec.level

        # make the parents references to the GO terms
        for rec in self.itervalues():
            rec.parents = [self[x] for x in rec._parents]

        # populate children and levels
        for rec in self.itervalues():
            for p in rec.parents:
                p.children.append(rec)

            if rec.level < 0:
                depth(rec)

    def write_dag(self, out=sys.stdout):
        for rec_id, rec in sorted(self.items()):
            print >>out, rec

    def query_term(self, term, verbose=False):
        if not term in self:
            logging.warning("Term %s not found!" % term)
            return

        rec = self[term]
        logging.info(str(rec))
        if verbose:
            logging.info("all parents:", rec.get_all_parents())
            logging.info("all children:", rec.get_all_children())

        return rec

    def paths_to_top(self, term, verbose=False):
        """ Returns all possible paths to the root node

            Each path includes the term given. The order of the path is
            top -> bottom, i.e. it starts with the root and ends with the
            given term (inclusively).

            Parameters:
            -----------
            - term:
                the id of the GO term, where the paths begin (i.e. the
                accession 'GO:0003682')

            Returns:
            --------
            - a list of lists of GO Terms
        """
        # error handling consistent with original authors
        if not term in self:
            logging.warning("Term %s not found!" % term)
            return

        def _paths_to_top_recursive(rec):
            if rec.level == 0:
                return [[rec]]
            paths = []
            for parent in rec.parents:
                top_paths = _paths_to_top_recursive(parent)
                for top_path in top_paths:
                    top_path.append(rec)
                    paths.append(top_path)
            return paths

        go_term = self[term]
        return _paths_to_top_recursive(go_term)

    def _label_wrap(self, label):
        wrapped_label = r"%s\n%s" % (label,
                                     self[label].name.replace(",", r"\n"))
        return wrapped_label

    def draw_lineage(self, recs, nodecolor="mediumseagreen",
                     edgecolor="lightslateblue", dpi=96,
                     lineage_img="GO_lineage.png", gml=False):
        # draw AMIGO style network, lineage containing one query record
        try:
            import pygraphviz as pgv
        except:
            logging.error("pygraphviz not installed, lineage not drawn!")
            logging.error("try `easy_install pygraphviz`")
            return

        G = pgv.AGraph()
        edgeset = set()
        for rec in recs:
            edgeset.update(rec.get_all_parent_edges())
            edgeset.update(rec.get_all_child_edges())

        edgeset = [(self._label_wrap(a), self._label_wrap(b))
                   for (a, b) in edgeset]
        for src, target in edgeset:
            # default layout in graphviz is top->bottom, so we invert
            # the direction and plot using dir="back"
            G.add_edge(target, src)

        G.graph_attr.update(dpi="%d" % dpi)
        G.node_attr.update(shape="box", style="rounded,filled",
                           fillcolor="beige", color=nodecolor)
        G.edge_attr.update(shape="normal", color=edgecolor,
                           dir="back", label="is_a")
        # highlight the query terms
        for rec in recs:
            try:
                q = G.get_node(self._label_wrap(rec.id))
                q.attr.update(fillcolor="plum")
            except:
                continue

        if gml:
            import networkx as nx  # use networkx to do the conversion
            pf = lineage_img.rsplit(".", 1)[0]
            G.name = "GO tree"
            NG = nx.from_agraph(G)

            del NG.graph['node']
            del NG.graph['edge']
            gmlfile = pf + ".gml"
            nx.write_gml(NG, gmlfile)

        logging.info("lineage info for terms %s written to %s" %
                     ([rec.id for rec in recs], lineage_img))

        G.draw(lineage_img, prog="dot")

    def update_association(self, association):
        bad_terms = set()
        for key, terms in association.items():
            parents = set()
            for term in terms:
                try:
                    parents.update(self[term].get_all_parents())
                except:
                    bad_terms.add(term)
            terms.update(parents)
        if bad_terms:
            logging.warning("terms not found: %s", bad_terms)

    def to_tree(self, root_id):
        """
        Use a BFS from the root to decide the level of each node in the graph.
        For each child, keep only one of the edges leading to it so it will
        have a single parent, from the previous level. Choose these edges 
        in a way which will keep the tree balanced (probably not optimally 
        though). This will assure that only one of the shortest paths from 
        the root to every node is kept.
        
        Input:
            dag  - a directer acyclic graph, format should be a dictionary
                   whose keys are all the node IDs and values are lists
                   of theirs children
            root - the ID of the node that should be the root of the tree
        """
        if root_id not in self:
            raise KeyError('The chosen root is not in the GODag %s:' % root_id)
        
        tree = Hierarchy()
        tree.create_node(self[root_id].name, root_id, parent=None)
        
        parents = set([root_id])
        
        while parents:
            children = set()
            
            child_to_parent_list = {}
            for parent in parents:
                for child in [c.id for c in self[parent].children]:
                    if tree.get_node(child) is not None:
                        continue
                    children.add(child)
                    child_to_parent_list.setdefault(child, []).append(parent)
    
            # the following list will contain pairs, counting the number of
            # children that each parent has.
            child_counts = [[0, p] for p in parents]
            for child, parent_list in child_to_parent_list.iteritems():
                # give this child to the parent with the least children
                for i, (counter, parent) in enumerate(child_counts):
                    if parent in parent_list:
                        break
                tree.create_node(self[child].name, child, parent)
                child_counts[i][0] += 1
                child_counts.sort()
            parents = children
            
        return tree
