# -*- coding: utf-8 -*-
"""Split compression command templates using the platform's quoting rules."""

__author__ = 'Shubham Padkonde'
__email__ = 'shubhampadkonde12@gmail.com'

import ctypes
import os
import shlex


def split_compression_command(command):
    """Split a command before interpolating log filenames into its arguments."""
    if os.name != 'nt':
        return shlex.split(command)

    # CommandLineToArgvW otherwise treats leading whitespace as an empty argv[0]
    # and an empty command as the current executable.
    command = command.lstrip()
    if not command:
        raise ValueError('Compression command must not be empty')

    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    split_command = shell32.CommandLineToArgvW
    split_command.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split_command.restype = ctypes.POINTER(ctypes.c_wchar_p)
    free_arguments = kernel32.LocalFree
    free_arguments.argtypes = [ctypes.c_void_p]
    free_arguments.restype = ctypes.c_void_p

    argc = ctypes.c_int()
    argv = split_command(command, ctypes.byref(argc))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return argv[:argc.value]
    finally:
        free_arguments(argv)
