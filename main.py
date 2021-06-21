#!/usr/bin/env python3

import os
import sys
import logging
import hashlib
from collections import OrderedDict
import mimetypes
import subprocess
from functools import lru_cache
from hmac import compare_digest
from pathlib import Path

import tornado.web
import tornado.template
import tornado.process

import config
from models import model
try:
  from checker import check_executable
except ImportError:
  async def check_executable(
    ip: str, sha1: str, content: bytes, filename: str,
  ) -> None:
    pass

SCRIPT_PATH = 'elimage'
RISKY_TYPES = [
  'application/x-dosexec',
  'application/x-executable',
  'application/x-pie-executable',
]

@lru_cache()
def guess_mime_using_file_p(path):
  with open(path, 'rb') as f:
    data = f.read()
  return guess_mime_using_file(data)

def guess_mime_using_file(content):
  result = subprocess.check_output(
    ['file', '--mime', '-'],
    input = content,
  ).decode()
  _, mime, encoding = result.split()
  mime = mime.rstrip(';')
  encoding = encoding.split('=')[-1]

  # older file doesn't know webp
  if mime == 'application/octet-stream':
    result = subprocess.check_output(
      ['file', '-'],
      input = content,
    ).decode()
    _, desc = result.split(None, 1)
    if 'Web/P image' in desc:
      return 'image/webp', None

  # Tornado will treat non-gzip encoding as application/octet-stream
  if encoding != 'gzip':
    encoding = None
  return mime, encoding

def qrencode(s):
  return subprocess.check_output(
    ['qrencode', '-t', 'UTF8', s]).decode()

# for StaticFileHandler
mimetypes.guess_type = guess_mime_using_file_p

def guess_extension(ftype):
  if ftype == 'application/octet-stream':
    return '.bin'
  elif ftype == 'image/webp':
    return '.webp'
  ext = mimetypes.guess_extension(ftype)
  if ext in ('.jpe', '.jpeg'):
    ext = '.jpg'
  return ext

def open_noatime(file, mode='r'):
  fd = os.open(file, os.O_RDONLY | os.O_NOATIME)
  return os.fdopen(fd, mode)

class BaseHandler(tornado.web.RequestHandler):
  def get(self, *args, **kwargs):
    raise tornado.web.HTTPError(404)

  async def _process_upload(self, method):
    # Check the user has been blocked or not
    user = model.get_user_by_ip(self.request.remote_ip)
    if user is None:
      uid = model.add_user(self.request.remote_ip)
    else:
      if user['blocked']:
        raise tornado.web.HTTPError(403, 'You are on our blacklist.')
      else:
        uid = user['id']

    # Check whether password is required
    expected_password = self.settings['password']
    if expected_password and \
      not compare_digest(self.get_argument('password'), expected_password):
        raise tornado.web.HTTPError(403, 'You need a valid password to post.')

    if method == 'POST':
      files = self.request.files
      if not files:
        raise tornado.web.HTTPError(400, 'upload your image please')
      filelist = [f for fs in files.values() for f in fs]
    elif method == 'PUT':
      filelist = [{
        'body': self.request.body,
        'filename': self.request.path,
      }]
    else:
      raise tornado.web.HTTPError(405)

    ret = OrderedDict()
    if method == 'PUT':
      # assume we are at / because we can't tell otherwise
      url_prefix = self.request.protocol + '://' + self.request.host
    else:
      url_prefix = self.request.full_url()
      if '?' in url_prefix:
        url_prefix = url_prefix.split('?', 1)[0]
      url_prefix = url_prefix.rstrip('/')

    for file in filelist:
      m = hashlib.sha1()
      m.update(file['body'])
      h = m.hexdigest()
      model.add_image(uid, h, file['filename'], len(file['body']))
      ftype = guess_mime_using_file(file['body'])[0]
      if ftype in RISKY_TYPES:
        await check_executable(
          self.request.remote_ip,
          h, file['body'], file['filename'])

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

      ext = None
      if ftype:
        ext = guess_extension(ftype)
      if ext:
        f += ext
      ret[file['filename']] = '%s/%s/%s' % (url_prefix, d, f)

    output_qr = self.get_argument('qr', None) is not None
    if len(ret) > 1:
      for item in ret.items():
        self.write('%s: %s\n' % item)
        if output_qr:
          self.write('%s\n' % qrencode(item[1]))
    elif ret:
      img_url = tuple(ret.values())[0]
      self.write("%s\n" % img_url)
      if output_qr:
        self.write('%s\n' % qrencode(img_url))
    logging.info('%s posted: %s', self.request.remote_ip, ret)

  async def put(self, *args, **kwargs):
    return await self._process_upload(method='PUT')

class IndexHandler(BaseHandler):
  index_template = None
  def get(self):
    # self.render() would compress whitespace after it meets '{{' even in <pre>
    if self.index_template is None:
      template_path = Path(self.settings['template_path'])
      try:
        file_name = template_path / 'index-site.html'
        try:
          with open(file_name) as index_file:
            text = index_file.read()
        except FileNotFoundError:
          file_name = template_path / 'index.html'
          with open(file_name) as index_file:
            text = index_file.read()

        self.__class__.index_template = tornado.template.Template(
          text, compress_whitespace=False)
      except IOError:
        logging.exception('failed to open the file: %s', file_name)
        raise tornado.web.HTTPError(404, 'index.html is missing')

    url_prefix = self.request.full_url()
    if '?' in url_prefix:
      url_prefix = url_prefix.split('?', 1)[0]

    content = self.index_template.generate(
      url=url_prefix,
      password_required=bool(self.settings['password'])
    )
    self.write(content)

  async def post(self):
    return await self._process_upload(method='POST')

class ToolHandler(BaseHandler):
  def get(self):
    self.set_header('Content-Type', 'text/x-python')
    self.render('elimage', url=self.request.full_url()[:-len(SCRIPT_PATH)])

class HashHandler(BaseHandler):
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

BOTS = [
  'Discordbot', 'TelegramBot', 'YandexImages', 'bingbot', 'Googlebot',
  'PetalBot', 'Pinterestbot', 'DotBot', 'MJ12bot', 'AhrefsBot',
  'aranhabot', 'DuckDuckBot', 'SeznamBot', 'Twitterbot', 'facebookexternalhit',
  'facebookexternalhit',
]

class FileHandler(tornado.web.StaticFileHandler, BaseHandler):
  def set_extra_headers(self, path):
    self.set_header("Cache-Control", "public, max-age=" + str(86400 * 365))

  async def get(self, path, include_body=True):
    try:
      await super().get(path, include_body)
    except tornado.web.HTTPError as e:
      if e.status_code == 404:
        self.set_status(404)
        self.set_header("Cache-Control", "public, max-age=86400")
        self.set_header("Content-Type", "text/plain")
        self.finish('404 Not Found\n')
      else:
        raise

  def get_content(self, abspath: str, start = None, end = None):
    try:
      ua = self.request.headers['User-Agent']
    except KeyError:
      raise tornado.web.HTTPError(500, "KeyError: 'User-Agent'")

    if any(bot in ua for bot in BOTS):
      opener = open_noatime
    else:
      opener = open

    with opener(abspath, "rb") as file:
      if start is not None:
        file.seek(start)
      if end is not None:
        remaining = end - (start or 0)
      else:
        remaining = None
      while True:
        chunk_size = 64 * 1024
        if remaining is not None and remaining < chunk_size:
          chunk_size = remaining
        chunk = file.read(chunk_size)
        if chunk:
          if remaining is not None:
            remaining -= len(chunk)
          yield chunk
        else:
          if remaining is not None:
            assert remaining == 0
          return

  def compute_etag(self):
    return None

def main():
  import tornado.httpserver
  from tornado.options import define, options

  from tornado.platform.asyncio import AsyncIOMainLoop
  import asyncio
  AsyncIOMainLoop().install()

  define("port", default=config.DEFAULT_PORT, help="run on the given port", type=int)
  define("address", default='', help="run on the given address", type=str)
  define("datadir", default=config.DEFAULT_DATA_DIR, help="the directory to put uploaded data", type=str)
  define("fork", default=False, help="fork after startup", type=bool)
  define("cloudflare", default=config.CLOUDFLARE, help="check for Cloudflare IPs", type=bool)
  define("password", default=config.UPLOAD_PASSWORD, help="optional password", type=str)

  tornado.options.parse_command_line()
  if options.fork:
    if os.fork():
      sys.exit()

  if options.cloudflare:
    import cloudflare
    cloudflare.install()
    loop = asyncio.get_event_loop()
    loop.create_task(cloudflare.updater())

  application = tornado.web.Application([
    (r"/", IndexHandler),
    (r"/" + SCRIPT_PATH, ToolHandler),
    (r"/([a-fA-F0-9]{2}/[a-fA-F0-9]{38})(?:\.\w*)?", FileHandler, {
      'path': options.datadir,
    }),
    (r"/([a-fA-F0-9/]+(?:\.\w*)?)", HashHandler),
    (r"/.*", BaseHandler),
  ],
    datadir=options.datadir,
    debug=config.DEBUG,
    template_path=os.path.join(os.path.dirname(__file__), "templates"),
    password=config.UPLOAD_PASSWORD,
  )
  http_server = tornado.httpserver.HTTPServer(
    application,
    xheaders=config.XHEADERS,
  )
  http_server.listen(options.port, address=options.address)

  asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    pass
