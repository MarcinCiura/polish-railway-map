#!/usr/bin/python

"""Scrape data on railway lines in Poland from HTML tables."""

import csv
import glob
import re
import sqlite3

import bs4


DATA_GLOB = 'semaforek.kolej.org.pl/wiki/index.php/*'

NUMBER_RE = re.compile(r'nr_\d\d?\d?')
KILOMETRAGE_RE = re.compile(r'\d+,\d(\d\d)?|b\.d\.')

SKIP_THIS_NAME = object()


def CreateDatabase(name):
  connection = sqlite3.connect(name)
  connection.executescript("""
      DROP TABLE IF EXISTS Names;
      DROP TABLE IF EXISTS Kinds;
      DROP TABLE IF EXISTS Lines;
      CREATE TABLE Names(
          name_id INTEGER PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          latitude REAL,
          longitude REAL
      );
      CREATE TABLE Kinds(
          kind_id INTEGER PRIMARY KEY,
          kind TEXT NOT NULL UNIQUE
      );
      CREATE TABLE Lines(
          point_id INTEGER PRIMARY KEY,
          line INTEGER NOT NULL,
          name_id INTEGER REFERENCES Names(name_id),
          kind_id INTEGER REFERENCES Kinds(kind_id),
          metrage INTEGER,
          other_line INTEGER
      );
      DROP INDEX IF EXISTS Names_name_idx;
      DROP INDEX IF EXISTS Kinds_kind_idx;
      DROP INDEX IF EXISTS Lines_line_metrage_idx;
      DROP INDEX IF EXISTS Lines_line_other_line_idx;
      DROP INDEX IF EXISTS Lines_name_id_idx;
      CREATE INDEX Names_name_idx ON Names(name);
      CREATE INDEX Kinds_kind_idx ON Kinds(kind);
      CREATE INDEX Lines_line_metrage_idx ON Lines(line, metrage);
      CREATE INDEX Lines_line_other_line_idx ON Lines(line, other_line);
      CREATE INDEX Lines_line_name_idx ON Lines(name_id);
  """)
  return connection


def Insert(cursor, line, name, lat, lon, kind, metrage, other_line):
  cursor.execute("""
      INSERT OR IGNORE INTO Names(name, latitude, longitude)
      VALUES(?, ?, ?)""", (name, lat, lon))
  if cursor.rowcount:
    name_id = cursor.lastrowid
  else:
    name_id = cursor.execute("""
        SELECT name_id FROM Names WHERE name = ?""", (name,)).fetchone()[0]

  kind_id = cursor.execute("""
      SELECT kind_id FROM Kinds WHERE kind = ?""", (kind,)).fetchone()
  if kind_id:
    kind_id = kind_id[0]
  else:
    cursor.execute("""
        INSERT OR IGNORE INTO Kinds(kind) VALUES(?)""", (kind,))
    kind_id = cursor.lastrowid

  cursor.execute("""
      INSERT INTO Lines(line, name_id, kind_id, metrage, other_line)
      VALUES(?, ?, ?, ?, ?)""", (line, name_id, kind_id, metrage, other_line))


def GetName(td):
  if td.find('del'):
    td.find('del').decompose()
  name = td.find_all('a')
  if name:
    name = name[0]['title']
    if name.endswith(' (strona nie istnieje)'):
      name = name[:-22]
    return name
  name = ' '.join(td.stripped_strings).strip()
  if name:
    return name
  return SKIP_THIS_NAME


def ToMeters(km):
  if km == 'b.d.':
    return None
  km = float(km.strip('()').replace(',', '.'))
  if km >= 0:
    return int(1000 * km + 0.5)
  else:
    return int(1000 * km - 0.5)


def GetKindAndMetrage(tds):
  td1 = None
  for i, td in enumerate(tds):
    td2 = td1
    if td.find('del'):
      td.find('del').decompose()
    td1 = ' '.join(td.stripped_strings).strip()
    if KILOMETRAGE_RE.search(td1):
      break
  return td2.replace('p.o.', 'przystanek osobowy'), ToMeters(td1)


def GetLines(td):
  result = []
  for line in td.find_all('a'):
    try:
      result.append(int(line.string))
    except UnicodeEncodeError:
      pass
  return result


def Process(table, filename, coord_dict, cursor):
  try:
    line = int(NUMBER_RE.search(filename).group(0)[3:])
  except AttributeError:
    line = int(filename.split('/')[-1])
  name_rowspan = 1
  first = True
  for tr in table.find_all('tr'):
    tds = tr.find_all('td')
    if not tds and not first:
      break
    if not 1 < len(tds) <= 6:
      continue
    if tds[1].get('colspan'):
      if tds[1].get('colspan') != '2' or len(tds) != 5:
        continue
    first = False
    name_rowspan -= 1
    if name_rowspan == 0:
      name_rowspan = tds[1].get('rowspan')
      name_rowspan = int(name_rowspan) if name_rowspan else 1
      new_name = GetName(tds[1])
      if new_name is SKIP_THIS_NAME:
        continue
      name = new_name
    kind, metrage = GetKindAndMetrage(tds)
    other_lines = GetLines(tds[-1])
    assert kind, (line, name, tds)
    lat, lon = coord_dict.get(name, (None, None))
    if other_lines:
      for other_line in other_lines:
        Insert(cursor, line, name, lat, lon, kind, metrage, other_line)
    else:
      Insert(cursor, line, name, lat, lon, kind, metrage, None)


def main():
  coord_dict = {}
  with open('coordinates.csv') as coordinates:
    for line in csv.reader(coordinates):
      coord_dict[line[0].decode('utf-8')] = (float(line[1]), float(line[2]))
  connection = CreateDatabase('id-12.sqlite')
  cursor = connection.cursor()
  for filename in glob.glob(DATA_GLOB):
    with open(filename) as f:
      soup = bs4.BeautifulSoup(f, 'lxml')
      for table in soup.find_all('table'):
        if len(table.tr.find_all('th')) == 5:
          Process(table, filename, coord_dict, cursor)
  connection.commit()
  connection.close()


if __name__ == '__main__':
  main()
