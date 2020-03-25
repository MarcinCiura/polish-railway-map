#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Draw a warped map of the railway network in Poland."""

import collections
import math
import sqlite3
import sys

import numpy
from matplotlib import collections as pyplot_collections
from matplotlib import pyplot
from sklearn import manifold

ABBREVIATIONS = {
    u'SG': u'Szczecin Główny-0',
    u'G': u'Gdańsk Główny-0',
    u'Ol': u'Olsztyn Główny-0',
    u'Bg': u'Bydgoszcz Główna-0',
    u'ZG': u'Zielona Góra-0',
    u'Po': u'Poznań Główny-0',
    u'WZ': u'Warszawa Zachodnia-0',
    u'Bł': u'Białystok-0',
    u'ŁK': u'Łódź Kaliska-0',
    u'Klc': u'Kielce-0',
    u'WG': u'Wrocław Główny-0',
    u'Op': u'Opole Główne-0',
    u'KO': u'Katowice-0',
    u'KG': u'Kraków Główny-0',
    u'Rz': u'Rzeszów Główny-0',
    u'Lb': u'Lublin-0',
}

class BiDict(object):

  def __init__(self):
    self.id_to_station = []
    self.station_to_id = {}

  def Add(self, station):
    if station in self.station_to_id:
      return
    self.station_to_id[station] = len(self.id_to_station)
    self.id_to_station.append(station)


def FindOrAddName(intersections, row, current, line):
  name = '%s-%d' % (row[0], row[1] - current[1])
  if row[2] is None:
    return name
  elif row[2] in intersections[line]:
    if len(intersections[line][row[2]]) == 1:
      return intersections[line][row[2]][0]
    name_candidates = [
        x for x in intersections[line][row[2]] if x.startswith(row[0])]
    if len(name_candidates) == 1:
      return name_candidates[0]
    else:
      return None
  else:
    if name not in intersections[row[2]][line]:
      intersections[row[2]][line].append(name)
    return name


def ReadEdges():
  edges = []
  connection = sqlite3.connect('id-12.sqlite')
  intersections = collections.defaultdict(lambda: collections.defaultdict(list))
  for line in xrange(1000):
    if line == 346:  # Liberec-Zittau, disconnected from the Polish network.
      continue
    rows = connection.execute("""
        SELECT name, metrage, other_line FROM Lines JOIN Names USING(name_id)
        WHERE line = ? ORDER BY metrage""", (line,)).fetchall()
    if not rows:
      continue
    i = 0
    while True:
      while i < len(rows):
        if rows[i][1] is not None:
          break
        i += 1
      if i == len(rows):
        break
      current = rows[i]
      previous_name = FindOrAddName(intersections, current, current, line)
      previous_metrage = current[1]
      if previous_name is not None:
        break
      i += 1
    assert previous_name is not None
    for row in rows[i + 1:]:
      if row[0] != current[0]:
        current = row
      if row[2] is None:
        continue
      name = FindOrAddName(intersections, row, current, line)
      if name is None or name == previous_name:
        continue
      if row[1] != previous_metrage:
        edges.append((previous_name, name, row[1] - previous_metrage))
        previous_name = name
        previous_metrage = row[1]
    if rows[-1][0] != current[0]:
      current = rows[-1]
    if rows[-1][2] is None:
      name = FindOrAddName(intersections, row, current, line)
      if name is not None and name != previous_name:
        if row[1] != previous_metrage:
          edges.append((previous_name, name, row[1] - previous_metrage))
  return edges


def BuildGraph(edges):
  stations = BiDict()
  for edge in edges:
    stations.Add(edge[0])
    stations.Add(edge[1])
  size = len(stations.id_to_station)
  graph = numpy.full((size, size), numpy.inf)
  for edge in edges:
    a = stations.station_to_id[edge[0]]
    b = stations.station_to_id[edge[1]]
    graph[a][b] = min(graph[a][b], edge[2])
    graph[b][a] = min(graph[b][a], edge[2])
  return graph, stations


def FloydWarshall(graph):
  n = graph.shape[0]
  I = numpy.identity(n)
  graph[I == 1] = 0
  for i in xrange(n):
    graph = numpy.minimum(
        graph, graph[numpy.newaxis, i, :] + graph[:, i, numpy.newaxis])
  return graph


def Draw(coords, edges, stations):
  figure = pyplot.figure(1)
  katowice = coords[stations.station_to_id[u'Katowice-0']]
  gdansk = coords[stations.station_to_id[u'Gdańsk Główny-0']]
  theta = math.atan2(gdansk[1] - katowice[1], gdansk[0] - katowice[0])
  theta -= math.pi / 2.0
  c = numpy.cos(theta)
  s = numpy.sin(theta)
  rotation = numpy.array([[c, -s], [s, c]])
  coords = numpy.dot(coords, rotation)
  lublin = coords[stations.station_to_id[u'Lublin-0']]
  if lublin[0] < katowice[0]:
    symmetry = numpy.array([[-1, 0], [0, 1]])
    coords = numpy.dot(coords, symmetry)
  pyplot.scatter(coords[:, 0], coords[:, 1], s=0)
  segments = [
      (coords[stations.station_to_id[x[0]]],
       coords[stations.station_to_id[x[1]]]) for x in edges]
  lc = pyplot_collections.LineCollection(segments, color='gray')
  pyplot.axes().set_aspect('equal')
  pyplot.axes().add_collection(lc)
  pyplot.axis('off')
  pyplot.gcf().set_size_inches(12, 12)
  pyplot.gcf().suptitle(
      'Polish railway network\n'
      'Euclidean distances on the map\ncorrespond to rail distances',
      fontsize=20, color='darkblue')
  pyplot.subplots_adjust(left=0, right=1, top=1, bottom=0)
  pyplot.plot([-3e5, -2e5], [-3e5, -3e5], '-', color='black')
  pyplot.text(
      -2.5e5, -3e5, '100 km',
      color='darkblue', ha='center', va='bottom', fontsize=20)
  for abbreviation, station in ABBREVIATIONS.iteritems():
    i = stations.station_to_id[station]
    pyplot.text(
        coords[i, 0], coords[i, 1], abbreviation,
        color='darkblue', fontsize=16)
  pyplot.savefig('pkp.png', bbox_inches='tight', pad_inches=0)


def main():
  print >>sys.stderr, 'Reading edges'
  edges = ReadEdges()
  print >>sys.stderr, 'Building sparse graph'
  graph, stations = BuildGraph(edges)
  print >>sys.stderr, 'Running Floyd-Warshall'
  graph = FloydWarshall(graph)
  print >>sys.stderr, 'Running MDS'
  mds = manifold.MDS(dissimilarity='precomputed')
  coords = mds.fit_transform(graph)
  print >>sys.stderr, 'Drawing map'
  Draw(coords, edges, stations)


if __name__ == '__main__':
  main()
