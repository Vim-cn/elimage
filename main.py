#!/usr/bin/env python3
# vim:fileencoding=utf-8

from config import *
from model import User, Image

import os
import time
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

@lru_cache()
def guess_mime_using_file(path):
  result = subprocess.check_output(['file', '-i', path]).decode()
  _, mime, encoding = result.split()
  mime = mime.rstrip(';')
  encoding = encoding.split('=')[-1]
  return mime, encoding
mimetypes.guess_type = guess_mime_using_file

class BaseHandler(tornado.web.RequestHandler):
  def initialize(self):
    if self.settings['host']:
      self.request.host = self.settings['host']

class IndexHandler(BaseHandler):
  index_template = None
  def get(self):
    # self.render() would compress whitespace after it meets '{{' even in <pre>
    if self.index_template is None:
      self.index_template = tornado.template.Template(
        open(os.path.join(self.settings['template_path'], 'index.html'), 'r').read(),
        compress_whitespace=False,
      )
    content = self.index_template.generate(url=self.request.full_url())
    self.write(content)

  def post(self):
    # Check the user has been blocked or not
    user_obj = User()
    user = user_obj.fetchone(('ip', self.request.remote_ip))
    if user is None:
      user_obj.ip = self.request.remote_ip
      user_obj.put()
      uid = user_obj.lastrowid
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
        #FIXME: avoid forgery
        if not (os.path.splitext(file['filename'])[1][1:].lower() in ('png', 'jpg', 'gif') \
                or file['content_type'].startswith('image/')):
          ret[file['filename']] = 'error: not an image.\n'
        else:
          m = hashlib.sha1()
          m.update(file['body'])
          h = m.hexdigest()
          img_obj = Image()
          if img_obj.get_by_name(h) is None:
            img_obj.uid = uid
            img_obj.name = h
            img_obj.time = int(time.time())
            img_obj.put()
          d = h[:2]
          f = h[2:]
          p = os.path.join(self.settings['datadir'], d)
          if not os.path.exists(p):
            os.mkdir(p, 0o750)
          fpath = os.path.join(p, f)
          if not os.path.exists(fpath):
            open(fpath, 'wb').write(file['body'])
          ret[file['filename']] = '%s/%s/%s\n' % (
              self.request.full_url().rstrip('/'), d, f
          )
    if len(ret) > 1:
      for i in ret.items():
        self.write('%s: %s'% i)
    elif ret:
      self.write(tuple(ret.values())[0])

def main():
  import tornado.httpserver
  from tornado.options import define, options
  define("port", default=DEFAULT_PORT, help="run on the given port", type=int)
  define("datadir", default=DEFAULT_DATA_DIR, help="the directory to put uploaded data", type=str)

  tornado.options.parse_command_line()
  application = tornado.web.Application([
    (r"/", IndexHandler),
    (r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})", tornado.web.StaticFileHandler, {
      'path': options.datadir,
    }),
  ],
    host=HOST,
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
    (PREFIX+r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})", tornado.web.StaticFileHandler, {
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
