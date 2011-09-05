An image paste service in favor of command line usage.

Usage
=====
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
* [https://github.com/lilydjwg/tornado/tree/lilydjwg](tornado with a patch)
