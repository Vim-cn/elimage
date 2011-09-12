#!/usr/bin/env python3
# vim: set fileencoding=utf-8:

import re
import sqlite3
import logging

from config import DB

#

__all__ = ['User', 'Image']

#

def log(fn):
  def wrapped(*args, **kwds):
    try:
      return fn(*args, **kwds)
    except Exception as e:
      logging.warning(e)
  return wrapped

#

class Database:
  def __init__(self, db):
    self.conn = sqlite3.connect(db)
    self.conn.row_factory = self.dict_factory
    self.cursor = self.conn.cursor()
    self.query = self.cursor.execute
    self.commit = self.conn.commit

  def dict_factory(self, cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
      d[col[0]] = row[idx]
    return d

  @log
  def q(self, sql):
    #print(sql)
    self.query(sql)
    return self.cursor.fetchall()


class Model(dict):
  __conn = None

  @classmethod
  def conn(cls, db):
    if not cls.__conn:
      cls.__conn = Database(db)

  def __init__(self, d={}):
    if not self.__conn:
      raise AttributeError
    dict.__init__(self, d)
    self.__dict__['table'] = self.__class__.__name__.lower()
    self.__dict__['where'] = ''
    self.__dict__['sql_buff'] = {}

  @property
  def lastrowid(self):
    return self.__conn.cursor.lastrowid

  def put(self):
    s = ''
    if self.where:
      f = []
      for k, v in self.sql_buff.items():
        f.append("%s='%s'"%(k, v))
        s = "update %s set %s where %s" % (
          self.table, ','.join(f), self.where)
    else:
      f , i= [], []
      for v in self.sql_buff:
        f.append(v)
        i.append(self.sql_buff[v])
      if f and i:
        s = "insert into %s (%s) values ('%s')" % (
        self.table, ','.join(f), "','".join(i))

    self.sql_buff = {}

    if s:
      self.__conn.query(s)
      self.__conn.commit()
    else:
      raise AttributeError

  def fetch(self, *args):
    f = args[0][0]
    v = args[0][1]

    if f is None or v is None:
      sql = 'select * from %s' % self.table
    else:
      f = str(f)
      v = str(v)
      sql = 'select * from %s where %s="%s"' % (self.table, f, v)

    r = self.__conn.q(sql)
    return r

  def fetchone(self, *args):
    r = self.fetch(*args)
    if r:
      return r[0]
    else:
      return None

  def __setattr__(self, attr, value):
    if attr in self.__dict__:
      self.__dict__[attr] = str(value)
    else:
      self.__dict__['sql_buff'][attr] = str(value)
      self[attr] = value

  def __getattr__(self, attr):
    if attr in self.__dict__:
      return self.__dict__[attr]
    try:
      return self[attr]
    except KeyError:
      pass
    raise AttributeError

#

Model.conn(DB)

class User(Model):
  def block(self, id, block=1):
    self.where = 'id=%s' % id
    self.blocked = block
    self.put()

  unblock = lambda self, id: self.block(id, block=0)

  def isBlocked(self, id):
    r = self.fetchone(('id', id))
    if r:
      return r['blocked'] == 1
    else:
      return False


class Image(Model):
  def get_by_name(self, name):
    r = self.fetchone(('name', name))
    return r

  def get_by_uid(self, uid):
    r = self.fetch(('uid', uid))
    return r

