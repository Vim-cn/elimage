#!/usr/bin/env python3
# vim:fileencoding=utf-8

import os
import hashlib
from collections import OrderedDict
import mimetypes
import subprocess

import tornado.web
import tornado.httpserver
from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)
define("datadir", default='.', help="the directory to put uploaded data", type=str)

def guess_mime_using_file(path):
  result = subprocess.check_output(['file', '-i', path]).decode()
  _, mime, encoding = result.split()
  mime = mime.rstrip(';')
  encoding = encoding.split('=')[-1]
  return mime, encoding
mimetypes.guess_type = guess_mime_using_file

class IndexHandler(tornado.web.RequestHandler):
  def get(self):
    #TODO
    self.write("curl -F 'name=@path/to/image' %s" % self.request.full_url())

  def post(self):
    files = self.request.files
    if not files:
      raise tornado.web.HTTPError(400, 'upload your image please')

    ret = OrderedDict()
    for filelist in files.values():
      for file in filelist:
        if not (os.path.splitext(file['filename'])[1][1:].lower() in ('png', 'jpg', 'gif') \
                or file['content_type'].startswith('image/')):
          self.write('ERROR: file %s is not an image.\n' % file['filename'])
        else:
          m = hashlib.sha1()
          m.update(file['body'])
          h = m.hexdigest()
          d = h[:2]
          f = h[2:]
          p = os.path.join(self.settings['datadir'], d)
          if not os.path.exists(p):
            os.mkdir(p, 0o750)
          fpath = os.path.join(p, f)
          if not os.path.exists(fpath):
            open(fpath, 'wb').write(file['body'])
          ret[file['filename']] = '%s://%s/%s/%s\n' % (
              self.request.protocol, self.request.host, d, f
          )
    if len(ret) > 1:
      for i in ret.items():
        self.write('%s: %s'% i)
    elif ret:
      self.write(tuple(ret.values())[0])

def main():
  tornado.options.parse_command_line()
  application = tornado.web.Application([
    (r"/", IndexHandler),
    (r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})", tornado.web.StaticFileHandler, {
      'path': options.datadir,
    }),
  ],
    datadir=options.datadir,
    debug=True,
  )
  http_server = tornado.httpserver.HTTPServer(application)
  http_server.listen(options.port)
  tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    pass
