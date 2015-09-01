An image paste service in favor of command line usage.

Usage
=====
Run it
------
Before you run it, you should configure the logging database. Rename
`elimage.db.sample` to match the one in `config.py`.

As a standalone web server, just execute it. As a WSGI application, you may
want to specify a new `PREFIX` pattern to meet your server configuration.

By default it runs at port `8888`, with `/tmp` as data directory to store image
files. Try option `--help` to know how to change them.

You can change some options in file `config.py`.

Upload images
-------------
Use the command line to upload image files and you'll get result URL printed.
You can specify multiple `-F` parameters for multiple image files. The name of
the form field doesn't matter.

```sh
curl -F 'name=@path/to/image' http://<your_host>/
```

Requirement
===========
* Python 2 or Python 3. Python 3.2+ is better as it makes use of [@lru_cache](http://docs.python.org/py3k/library/functools.html#functools.lru_cache)
* The `file` command
* [tornado](https://github.com/facebook/tornado). A recent version (after [commit 39de229](https://github.com/facebook/tornado/commit/39de229e86bc67df62dd3bb40dd43245cb120295)) if using Python 3+.

TODO
====
* record the original image filename
