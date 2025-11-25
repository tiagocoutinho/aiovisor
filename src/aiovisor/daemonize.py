import os
import grp
import pwd
import fcntl
import logging
import resource
import contextlib


log = logging.getLogger("aiovisor.daemonize")


@contextlib.contextmanager
def daemonize(
    app, pidfile=None, user=None, group=None, chdir=None, umask=0o27, foreground=False
):
    lockfile = prepare_pidfile(pidfile)
    parent_pid = os.getpid()
    try:
        _daemonize(app, lockfile, user, group, chdir, umask, foreground)
        yield
    finally:
        if foreground or parent_pid != os.getpid():
            try:
                os.remove(pidfile)
            except FileNotFoundError:
                pass


def prepare_pidfile(pidfile):
    # If pidfile already exists, we should read pid from there; to overwrite
    # it, if locking will fail, because locking attempt somehow purges the
    # file contents.
    if os.path.isfile(pidfile):
        with open(pidfile, "r") as old_pidfile:
            old_pid = old_pidfile.read()

    # Create a lockfile so that only one instance of this daemon is running at any time.
    lockfile = open(pidfile, "w")

    try:
        # Try to get an exclusive lock on the file. This will fail if another
        # process has the file locked.
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        lockfile.close()
        # Restore pid file content
        with open(pidfile, "w") as lockfile:
            lockfile.write(old_pid)
        raise
    return lockfile


def _daemonize(app, lockfile, user, group, chdir, umask, foreground):
    """Raises OSError or KeyError"""
    # skip fork if foreground is specified
    if not foreground:
        # Fork, creating a new process for the child.
        process_id = os.fork()

        if process_id != 0:
            exit(0)

        # This is the child process. Continue.

        # Stop listening for signals that the parent process receives.
        # This is done by getting a new process id.
        # setpgrp() is an alternative to setsid().
        # setsid puts the process in a new parent group and detaches its controlling terminal.
        process_id = os.setsid()
        if process_id == -1:
            raise OSError("Unable to create session")

        # Close all file descriptors
        devnull = getattr(os, "devnull", "/dev/null")

        lockfile_fd = lockfile.fileno()
        max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        os.closerange(3, lockfile_fd)
        os.closerange(lockfile_fd + 1, max_fd)

        devnull_fd = os.open(devnull, os.O_RDWR)
        os.dup2(devnull_fd, 0)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)

    # Set umask to default to safe file permissions when running as a root daemon. 027 is an
    # octal number which we are typing as 0o27 for Python3 compatibility.
    os.umask(umask)

    # Change to a known directory.
    if chdir:
        os.chdir(chdir)

    # Change owner of pid file, it's required because pid file will be removed at exit.
    uid, gid = -1, -1

    if group:
        gid = grp.getgrnam(group).gr_gid

    if user:
        uid = pwd.getpwnam(user).pw_uid

    if uid != -1 or gid != -1:
        os.chown(lockfile.name, uid, gid)

    # Change gid
    if group:
        os.setgid(gid)

    # Change uid
    if user:
        uid = pwd.getpwnam(user).pw_uid
        os.setuid(uid)

    lockfile.write("%s" % (os.getpid()))
    lockfile.flush()
