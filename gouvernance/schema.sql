CREATE TABLE profils (
  code   TEXT PRIMARY KEY,
  libelle TEXT,
  actif  INTEGER DEFAULT 1
);

CREATE TABLE tools (
  code        TEXT PRIMARY KEY,
  description TEXT
);

CREATE TABLE collections (
  code    TEXT PRIMARY KEY,
  libelle TEXT
);

CREATE TABLE profil_tool (
  profil TEXT REFERENCES profils(code),
  tool   TEXT REFERENCES tools(code),
  PRIMARY KEY (profil, tool)
);

CREATE TABLE profil_collection (
  profil     TEXT REFERENCES profils(code),
  collection TEXT REFERENCES collections(code),
  PRIMARY KEY (profil, collection)
);

CREATE TABLE profil_table (
  profil               TEXT REFERENCES profils(code),
  table_sql            TEXT,
  lecture_seule_schema INTEGER DEFAULT 0,
  PRIMARY KEY (profil, table_sql)
);

CREATE TABLE colonne_interdite (
  profil    TEXT REFERENCES profils(code),
  table_sql TEXT,
  colonne   TEXT,
  motif     TEXT,
  PRIMARY KEY (profil, table_sql, colonne)
);

CREATE TABLE identites (
  sujet  TEXT PRIMARY KEY,
  profil TEXT REFERENCES profils(code),
  source TEXT
);
