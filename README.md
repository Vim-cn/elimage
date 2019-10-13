An image paste service in favor of command line usage.

Usage
=====
Run it
------
Before you run it, you should configure the logging database. Rename
`elimage.db.sample` to match the one in `config.py`.

Run `./main.py` to start the server.

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
* Python 3.5+
* The `file` command
* [tornado](https://github.com/facebook/tornado) 3.2+
* The `qrencode` command if you want support for QR-code output
