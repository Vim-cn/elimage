#!/usr/bin/env python

import sys, os, time, atexit
from signal import SIGTERM

class Daemon:
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.pidfile = pidfile
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def daemonize(self):
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        os.chdir("/")
        os.setsid()
        os.umask(0)

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        sys.stdin.flush()
        sys.stdout.flush()
        sys.stderr.flush()

        si = file(self.stdin, 'r')
        os.dup2(si.fileno(), sys.stdin.fileno())
        so = file(self.stdout, 'a+')
        os.dup2(so.fileno(), sys.stdout.fileno())
        se = file(self.stderr, 'a+', 0)
        os.dup2(se.fileno(), sys.stderr.fileno())

        atexit.register(self.delpid)
        file(self.pidfile, 'w+').write("%s\n" % os.getpid())

    def delpid(self):
        os.remove(self.pidfile)

    def _getpid(self):
        try:
            pf = file(self.pidfile, 'r')
            pid = "%s" % pf.read().strip()
            pf.close()
            return int(pid)
        except IOError:
            return None

    def start(self):
        if self._getpid():
             message = "pidfile %s already exist. Daemon already running?\n"
             sys.stderr.write(message % self.pidfile)
             sys.exit(1)

        self.daemonize()
        self.run()

    def stop(self):
        pid = self._getpid()
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart

        try:
            while True:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
                else:
                    print str(err)
                    sys.exit(1)

    def restart(self):
        self.stop()
        self.start()

    def run(self):
        import main
        main.main()

if __name__ == "__main__":
    daemon = Daemon('/tmp/daemon-example.pid')
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            daemon.start()
        elif 'stop' == sys.argv[1]:
            daemon.stop()
        elif 'restart' == sys.argv[1]:
            daemon.restart()
        else:
            print "Unknown command"
            sys.exit(2) 
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart" % sys.argv[0]
        sys.exit(2)
