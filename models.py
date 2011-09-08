#!/usr/bin/env python3
# vim: set fileencoding=utf-8:

import sqlite3
import logging
import time

from config import DB

#

__all__ = ['model']

#

logging.basicConfig(filename='dberror.log')
def log(fn):
  def wrapped(*args, **kwds):
    try:
      return fn(*args, **kwds)
    except Exception as e:
      logging.warning(e)
  return wrapped

def dict_factory(cursor, row):
  d = {}
  for idx, col in enumerate(cursor.description):
    d[col[0]] = row[idx]
  return d

#

class Model:
  def __init__(self, db):
    self.conn = sqlite3.connect(db)
    self.conn.row_factory = dict_factory
    self.cur = self.conn.cursor()

  @log
  def get_user_by_id(self, id):
    row = self.cur.execute('select * from user where id=?', (id,))
    return row.fetchone()

  @log
  def get_user_by_ip(self, ip):
    row = self.cur.execute('select * from user where ip=?', (ip,))
    return row.fetchone()

  @log
  def get_image_by_name(self, name):
    row = self.cur.execute('select * from image where name=?', (name,))
    return row.fetchone()

  @log
  def get_image_by_uid(self, uid):
    row = self.cur.execute('select * from image where uid=?', (uid,))
    return row.fetchall()

  @log
  def add_user(self, ip):
    self.cur.execute('insert into user(ip) values (?)', (ip,))
    self.conn.commit()
    return self.cur.lastrowid

  @log
  def add_image(self, uid, fname):
    self.cur.execute('insert into image(uid, name, time) values (?, ?, ?)',
                     (uid, fname, int(time.time())))
    self.conn.commit()

  @log
  def block_user(self, id, block=1):
    self.cur.execute('update user set blocked=? where id=?', (block, id))
    self.conn.commit()

  unblock_user = lambda self, id: self.block_user(id, block=0)

  def isBlocked(self, type, data):
    method = getattr(self, 'get_user_by_'+type, None)
    if callable(method):
      row = method(data)
    return row['blocked'] == 1

#

model = Model(DB)
