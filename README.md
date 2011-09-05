An image paste service in favor of command line usage.

Usage
=====
Run it
------
Just execute it!

By default it runs at port `8888`, with current working directory as data
directory to store image files. Try option `--help` to know how to change them.

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
* Python 3.2+
* The `file` command
* [tornado with a patch](https://github.com/lilydjwg/tornado/tree/lilydjwg)
