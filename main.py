#!/usr/bin/env python3

from config import *
from models import model

import os
import sys
import logging
import hashlib
from collections import OrderedDict
import mimetypes
import subprocess

try:
  from functools import lru_cache
except ImportError:
  # fallback
  def lru_cache():
    def wrapper(func):
      def wrapper2(path):
        return func(path)
      return wrapper2
    return wrapper

import tornado.web
import tornado.template

SCRIPT_PATH = 'elimage'

@lru_cache()
def guess_mime_using_file(path):
  result = subprocess.check_output(['file', '-i', path]).decode()
  _, mime, encoding = result.split()
  mime = mime.rstrip(';')
  encoding = encoding.split('=')[-1]

  if mime == 'application/octet-stream':
    result = subprocess.check_output(['file', path]).decode()
    _, desc = result.split(None, 1)
    if 'Web/P image' in desc:
      return 'image/webp', 'binary'

  return mime, encoding

mimetypes.guess_type = guess_mime_using_file

def guess_extension(ftype):
  if ftype == 'application/octet-stream':
    return '.bin'
  elif ftype == 'image/webp':
    return '.webp'
  ext = mimetypes.guess_extension(ftype)
  if ext in ('.jpe', '.jpeg'):
    ext = '.jpg'
  return ext

class IndexHandler(tornado.web.RequestHandler):
  index_template = None
  def get(self):
    # self.render() would compress whitespace after it meets '{{' even in <pre>
    if self.index_template is None:
      try:
        file_name = os.path.join(self.settings['template_path'], 'index.html')
        with open(file_name, 'r') as index_file:
          text = index_file.read()
      except IOError:
        logging.exception('failed to open the file: %s', file_name)
        raise tornado.web.HTTPError(404, 'index.html is missing')
      else:
        self.index_template = tornado.template.Template(
          text, compress_whitespace=False)
        content = self.index_template.generate(url=self.request.full_url())
        self.write(content)

  def post(self):
    # Check the user has been blocked or not
    user = model.get_user_by_ip(self.request.remote_ip)
    if user is None:
      uid = model.add_user(self.request.remote_ip)
    else:
      if user['blocked']:
        raise tornado.web.HTTPError(403, 'You are on our blacklist.')
      else:
        uid = user['id']

    files = self.request.files
    if not files:
      raise tornado.web.HTTPError(400, 'upload your image please')

    ret = OrderedDict()
    for filelist in files.values():
      for file in filelist:
        m = hashlib.sha1()
        m.update(file['body'])
        h = m.hexdigest()
        model.add_image(uid, h)
        d = h[:2]
        f = h[2:]
        p = os.path.join(self.settings['datadir'], d)
        if not os.path.exists(p):
          os.mkdir(p, 0o750)
        fpath = os.path.join(p, f)
        if not os.path.exists(fpath):
          try:
            with open(fpath, 'wb') as img_file:
              img_file.write(file['body'])
          except IOError:
            logging.exception('failed to open the file: %s', fpath)
            ret[file['filename']] = 'FAIL'
            self.set_status(500)
            continue

        ftype = mimetypes.guess_type(fpath)[0]
        ext = None
        if ftype:
          ext = guess_extension(ftype)
        if ext:
          f += ext
          ret[file['filename']] = '%s/%s/%s' % (
            self.request.full_url().rstrip('/'), d, f)

    if len(ret) > 1:
      for item in ret.items():
        self.write('%s: %s\n' % item)
    elif ret:
      img_url = tuple(ret.values())[0]
      self.write("%s\n" % img_url)

class ToolHandler(tornado.web.RequestHandler):
  def get(self):
    self.set_header('Content-Type', 'text/x-python')
    self.render('elimage', url=self.request.full_url()[:-len(SCRIPT_PATH)])

class HashHandler(tornado.web.RequestHandler):
  def get(self, p):
    if '.' in p:
      h, ext = p.split('.', 1)
      ext = '.' + ext
    else:
      h, ext = p, ''

    h = h.replace('/', '')
    if len(h) != 40:
      raise tornado.web.HTTPError(404)
    else:
      self.redirect('/%s/%s%s' % (h[:2], h[2:], ext), permanent=True)

def main():
  import tornado.httpserver
  from tornado.options import define, options

  define("port", default=DEFAULT_PORT, help="run on the given port", type=int)
  define("datadir", default=DEFAULT_DATA_DIR, help="the directory to put uploaded data", type=str)
  define("fork", default=False, help="fork after startup", type=bool)

  tornado.options.parse_command_line()
  if options.fork:
    if os.fork():
      sys.exit()

  application = tornado.web.Application([
    (r"/", IndexHandler),
    (r"/" + SCRIPT_PATH, ToolHandler),
    (r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})(?:\.\w*)?", tornado.web.StaticFileHandler, {
      'path': options.datadir,
    }),
    (r"/([a-fA-F0-9/]+(?:\.\w*)?)", HashHandler),
  ],
    datadir=options.datadir,
    debug=DEBUG,
    template_path=os.path.join(os.path.dirname(__file__), "templates"),
  )
  http_server = tornado.httpserver.HTTPServer(application,
                                              xheaders=XHEADERS)
  http_server.listen(options.port)
  tornado.ioloop.IOLoop.instance().start()

def wsgi():
  import tornado.wsgi
  global application
  application = tornado.wsgi.WSGIApplication([
    (PREFIX+r"/", IndexHandler),
    (PREFIX+r"/" + SCRIPT_PATH, ToolHandler),
    (PREFIX+r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})(?:\.\w*)", tornado.web.StaticFileHandler, {
      'path': DEFAULT_DATA_DIR,
    }),
  ],
    datadir=DEFAULT_DATA_DIR,
    debug=DEBUG,
    template_path=os.path.join(os.path.dirname(__file__), "templates"),
  )

if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    pass
else:
  wsgi()
