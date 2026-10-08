"""Regression tests for compressed log file paths."""

import os
from unittest.mock import patch

import pytest

from moler.util.compressed_rotating_file_handler import CompressedRotatingFileHandler
from moler.util.compressed_timed_rotating_file_handler import CompressedTimedRotatingFileHandler
from moler.util.compression_command import split_compression_command


@pytest.mark.parametrize('handler_class', [CompressedRotatingFileHandler, CompressedTimedRotatingFileHandler])
@pytest.mark.parametrize('name', ['plain.log', 'log with spaces.log', "quoted'log.log"])
def test_compression_preserves_file_arguments(tmp_path, handler_class, name):
    filename = tmp_path / name
    filename.touch()
    handler = handler_class(filename=str(filename), delay=True)
    with patch('subprocess.Popen') as popen:
        try:
            handler._compress_file(str(filename))
            popen.assert_called_once_with(['zip', '-9mq', str(filename) + '.zip', str(filename)])
        finally:
            handler.close()


@pytest.mark.parametrize('handler_class', [CompressedRotatingFileHandler, CompressedTimedRotatingFileHandler])
def test_compression_preserves_quoted_command_arguments(tmp_path, handler_class):
    filename = tmp_path / 'test.log'
    filename.touch()
    handler = handler_class(filename=str(filename), delay=True,
                            compress_command='"custom compressor" --label "test logs" {compressed} {log_input}')
    with patch('subprocess.Popen') as popen:
        try:
            handler._compress_file(str(filename))
            popen.assert_called_once_with(['custom compressor', '--label', 'test logs',
                                          str(filename) + '.zip', str(filename)])
        finally:
            handler.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows command line parsing')
@pytest.mark.parametrize('handler_class', [CompressedRotatingFileHandler, CompressedTimedRotatingFileHandler])
@pytest.mark.parametrize('command, expected', [
    (r'C:\tools\7z.exe a {compressed} {log_input}', [r'C:\tools\7z.exe', 'a']),
    (r'"C:\Program Files\7-Zip\7z.exe" a {compressed} {log_input}',
     [r'C:\Program Files\7-Zip\7z.exe', 'a']),
    (r'\\server\tools\7z.exe a -w"C:\working directory" {compressed} {log_input}',
     [r'\\server\tools\7z.exe', 'a', r'-wC:\working directory']),
    (r"C:\O'Brien\7z.exe a {compressed} {log_input}", [r"C:\O'Brien\7z.exe", 'a']),
    (r'7z.exe a --label "say \"hi\"" {compressed} {log_input}', ['7z.exe', 'a', '--label', 'say "hi"']),
    (r'7z.exe a -w "C:\working directory\\" {compressed} {log_input}',
     ['7z.exe', 'a', '-w', 'C:\\working directory\\']),
    (r'  C:\tools\7z.exe a {compressed} {log_input}', [r'C:\tools\7z.exe', 'a']),
])
def test_compression_preserves_windows_command_paths(tmp_path, handler_class, command, expected):
    filename = tmp_path / "log with 'quotes'.log"
    filename.touch()
    handler = handler_class(filename=str(filename), delay=True, compress_command=command)
    with patch('subprocess.Popen') as popen:
        try:
            handler._compress_file(str(filename))
            popen.assert_called_once_with(expected + [str(filename) + '.zip', str(filename)])
        finally:
            handler.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows command line parsing')
@pytest.mark.parametrize('command', ['', '   '])
def test_empty_windows_compression_command_is_rejected(command):
    with pytest.raises(ValueError, match='Compression command must not be empty'):
        split_compression_command(command)


@pytest.mark.parametrize('handler_class', [CompressedRotatingFileHandler, CompressedTimedRotatingFileHandler])
def test_compression_preserves_posix_escaped_options(tmp_path, handler_class):
    filename = tmp_path / 'test.log'
    filename.touch()
    command = r'custom\ compressor --label test\ logs {compressed} {log_input}'
    handler = handler_class(filename=str(filename), delay=True, compress_command=command)
    with patch('os.name', 'posix'), patch('subprocess.Popen') as popen:
        try:
            handler._compress_file(str(filename))
            popen.assert_called_once_with(['custom compressor', '--label', 'test logs',
                                          str(filename) + '.zip', str(filename)])
        finally:
            handler.close()
