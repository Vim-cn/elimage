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
from os.path import splitext
import signal

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
import tornado.gen
import tornado.process

SCRIPT_PATH = 'elimage'

@lru_cache()
def guess_mime_using_file(path):
  result = subprocess.check_output(['file', '-i', path]).decode()
  _, mime, encoding = result.split()
  mime = mime.rstrip(';')
  encoding = encoding.split('=')[-1]

  # older file doesn't know webp
  if mime == 'application/octet-stream':
    result = subprocess.check_output(['file', path]).decode()
    _, desc = result.split(None, 1)
    if 'Web/P image' in desc:
      return 'image/webp', None

  # Tornado will treat non-gzip encoding as application/octet-stream
  if encoding != 'gzip':
    encoding = None
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

def splitext_(path):
    for ext in ['.tar.gz', '.tar.bz2', '.tar.xz']:
        if path.endswith(ext):
            return path[:-len(ext)], path[-len(ext):]
        return splitext(path)

@tornado.gen.coroutine
def convert_webp(webp, png):
  cmd = ['dwebp', webp, '-o', png]
  # cmd = ['convert', '-interlace', 'PNG', webp, png]
  logging.info('convert webp to png: %s', webp)
  p = tornado.process.Subprocess(cmd, stderr=subprocess.DEVNULL)
  yield p.wait_for_exit()

class IndexHandler(tornado.web.RequestHandler):
  index_template = None
  link_template = None

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

        filename = file['filename']
        ftype = mimetypes.guess_type(fpath)[0]
        ext = None
        if ftype:
          ext = guess_extension(ftype)

        if ext:
          f += ext
        else:
          _, ext = splitext_(filename)
          f += ext

        headers = self.request.headers
        ret[filename] = '%s://%s/%s/%s' % (
                headers.get('X-Scheme', self.request.protocol),
                self.request.host,
                d, f)

    if self.link_template is None:
       try:
         file_name = os.path.join(self.settings['template_path'], 'link.html')
         with open(file_name, 'r') as link_file:
           text = link_file.read()
        except IOError:
          raise tornado.web.HTTPError(404, 'link.html is missing')
        else:
          self.link_template = tornado.template.Template(
                  text, compress_whitespace=False)

    if len(ret) > 1:
      for item in ret.items():
        self.write('%s: %s\n' % item)
    elif ret:
      img_url = tuple(ret.values())[0]
      content = self.index_template.generate(url=img_url)
      self.write(content)

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

class MyStaticFileHandler(tornado.web.StaticFileHandler):
  '''dirty hack for webp images'''

  @tornado.gen.coroutine
  def get(self, path, include_body=True):
    self.path = self.parse_url_path(path)
    absolute_path = self.get_absolute_path(self.root, self.path)
    self.absolute_path = self.validate_absolute_path(self.root, absolute_path)
    if self.absolute_path is None:
      return

    content_type = self.get_content_type()
    headers = self.request.headers
    if self.absolute_path.endswith('.png') or self.request.method != 'GET' \
       or content_type != 'image/webp':
      yield super(MyStaticFileHandler, self).get(path, include_body=include_body)
      return

    self.set_header('Vary', 'User-Agent, Accept')
    if 'image/webp' in headers.get('Accept', '').lower() \
       or 'Gecko' not in headers.get('User-Agent', ''):
      yield super(MyStaticFileHandler, self).get(path, include_body=include_body)
      return

    png_path = self.absolute_path + '.png'
    if not os.path.exists(png_path):
      yield convert_webp(self.absolute_path, png_path)

    path += '.png'
    yield super(MyStaticFileHandler, self).get(path, include_body=include_body)

def signal_handler(signo, frame):
    os.execl('/usr/bin/python', '/usr/bin/python', *sys.argv)

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

  pidfile = file(PID_FILE, 'w')
  pidfile.write(str(os.getpid()))
  pidfile.flush()

  application = tornado.web.Application([
    (r"/", IndexHandler),
    (r"/" + SCRIPT_PATH, ToolHandler),
    (r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})(?:\.\w*)?", MyStaticFileHandler, {
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
  signal.signal(signal.SIGHUP, signal_handler)

  tornado.ioloop.IOLoop.instance().start()

def wsgi():
  import tornado.wsgi
  global application
  application = tornado.wsgi.WSGIApplication([
    (PREFIX+r"/", IndexHandler),
    (PREFIX+r"/" + SCRIPT_PATH, ToolHandler),
    (PREFIX+r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})(?:\.\w*)", MyStaticFileHandler, {
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
