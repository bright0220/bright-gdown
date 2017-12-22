#!/usr/bin/env python

from __future__ import print_function

import argparse
import os
import os.path as osp
import pkg_resources
import re
import shutil
import sys
import tempfile

import requests
import tqdm


__author__ = 'Kentaro Wada <www.kentaro.wada@gmail.com>'
__version__ = pkg_resources.get_distribution('gdown').version


this_dir = osp.dirname(osp.realpath(__file__))


def get_url_from_gdrive_confirmation(contents):
    url = ''
    for line in contents.splitlines():
        m = re.search('href="(\/uc\?export=download[^"]+)', line)
        if m:
            url = 'https://docs.google.com' + m.groups()[0]
            url = url.replace('&amp;', '&')
            return url
        m = re.search('confirm=([^;&]+)', line)
        if m:
            confirm = m.groups()[0]
            url = re.sub(r'confirm=([^;&]+)', r'confirm='+confirm, url)
            return url
        m = re.search('"downloadUrl":"([^"]+)', line)
        if m:
            url = m.groups()[0]
            url = url.replace('\\u003d', '=')
            url = url.replace('\\u0026', '&')
            return url


def _is_google_drive_url(url):
    m = re.match('^https?://drive.google.com/uc\?id=.*$', url)
    return m is not None


def download(url, output, quiet, with_id=False):
    if with_id:
        url = 'https://drive.google.com/uc?id={id}'.format(id=url)

    url_origin = url
    sess = requests.session()

    is_gdrive = _is_google_drive_url(url)

    while True:
        res = sess.get(url, stream=True)
        if 'Content-Disposition' in res.headers:
            # This is the file
            break
        if not is_gdrive:
            break

        # Need to redirect with confiramtion
        url = get_url_from_gdrive_confirmation(res.text)

        if url is None:
            print('Permission denied: %s' % url_origin, file=sys.stderr)
            print("Maybe you need to change permission over "
                  "'Anyone with the link'?", file=sys.stderr)
            return

    if output is None:
        if is_gdrive:
            m = re.search('filename="(.*)"',
                          res.headers['Content-Disposition'])
            output = m.groups()[0]
        else:
            output = osp.basename(url)

    if not quiet:
        print('Downloading...')
        print('From: %s' % url_origin)
        print('To: %s' % osp.abspath(output))

    tmp_file = tempfile.mktemp(output)
    try:
        with open(tmp_file, 'wb') as f:
            total = res.headers.get('Content-Length')
            if total is not None:
                total = int(total)
            if not quiet:
                pbar = tqdm.tqdm(total=total, unit='B', unit_scale=True)
            chunk_size = 1024  # bytes
            for chunk in res.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                if not quiet:
                    pbar.update(len(chunk))
            if not quiet:
                pbar.close()
        shutil.copy(tmp_file, output)
    finally:
        os.remove(tmp_file)

    return output


class _ShowVersionAction(argparse.Action):
    def __init__(self, *args, **kwargs):
        kwargs['nargs'] = 0
        self.version = kwargs.pop('version')
        super(self.__class__, self).__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print('gdown {ver} at {pos}'
              .format(ver=self.version, pos=this_dir))
        parser.exit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-V', '--version', version=__version__,
                        action=_ShowVersionAction)
    parser.add_argument('url', help='URL to download file from.')
    parser.add_argument('-O', '--output', default=None,
                        help='Output filename.')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress standard output.')
    parser.add_argument('--id', action='store_true')
    args = parser.parse_args()

    download(
        url=args.url,
        output=args.output,
        quiet=args.quiet,
        with_id=args.id,
    )


if __name__ == '__main__':
    main()
