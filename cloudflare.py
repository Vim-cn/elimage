import ipaddress
import asyncio
import logging

import tornado.web
from tornado.httpclient import AsyncHTTPClient
from tornado.platform.asyncio import to_asyncio_future

CLOUDFLARE_IPS = []

logger = logging.getLogger(__name__)

async def update_cloudflare_ips():
  global CLOUDFLARE_IPS

  urls = ['https://www.cloudflare.com/ips-v4',
          'https://www.cloudflare.com/ips-v6']
  client = AsyncHTTPClient()
  coros = [to_asyncio_future(client.fetch(url)) for url in urls]
  rs, _ = await asyncio.wait(coros)

  new = []
  for r in rs:
    r = r.result()
    new.extend(ipaddress.ip_network(line)
               for line in r.body.decode('utf-8').splitlines())
  CLOUDFLARE_IPS = new

async def updater():
  while True:
    try:
      await update_cloudflare_ips()
      logger.info('cloudflare ips updated.')
    except Exception:
      logger.exception('error when update cloudflare ips')
    await asyncio.sleep(24 * 3600)

def install():
  RH = tornado.web.RequestHandler
  RH.prepare = _my_prepare

def _my_prepare(self):
  request = self.request
  cfip = request.headers.get('Cf-Connecting-IP')
  if cfip:
    ip = ipaddress.ip_address(request.remote_ip)
    for net in CLOUDFLARE_IPS:
      if ip in net:
        request.remote_ip = cfip
        request.protocol = request.headers.get('X-Forwarded-Proto', 'http')
        break
