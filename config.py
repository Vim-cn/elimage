#!/usr/bin/env python3
# vim:fileencoding=utf-8

DEBUG = True
DEFAULT_DATA_DIR = '/tmp'
DEFAULT_PORT = 8888
HOST = '' # override Host header, useful when behind another server
XHEADERS = True # you may set this to false if not behind another server
DB = 'elimage.db'

PREFIX = r'/elimage' # For WSGI. this is a regex
