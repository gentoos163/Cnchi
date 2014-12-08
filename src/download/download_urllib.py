#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  download_urllib.py
#
#  Copyright © 2013,2014 Antergos
#
#  This file is part of Cnchi.
#
#  Cnchi is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  Cnchi is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Cnchi; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

""" Module to download packages using urllib """

import os
import logging
import queue
import shutil
import urllib.request
import urllib.error

try:
    _("")
except NameError as err:
    def _(message): return message

def url_open_read(urlp, chunk_size=8192):
    """ Helper function to download and read a fragment of a remote file """

    download_error = True
    data = None

    try:
        data = urlp.read(chunk_size)
        download_error = False
    except urllib.error.HTTPError as err:
        msg = ' HTTPError : %s' % err.reason
        logging.warning(msg)
    except urllib.error.URLError as err:
        msg = ' URLError : %s' % err.reason
        logging.warning(msg)

    return (data, download_error)

def url_open(url):
    """ Helper function to open a remote file """

    msg = _('Error opening %s:') % url

    if url is None:
        logging.warning(msg)
        return None

    try:
        urlp = urllib.request.urlopen(url)
    except urllib.error.HTTPError as err:
        urlp = None
        msg += ' HTTPError : %s' % err.reason
        logging.warning(msg)
    except urllib.error.URLError as err:
        urlp = None
        msg += ' URLError : %s' % err.reason
        logging.warning(msg)
    except AttributeError as err:
        urlp = None
        msg += ' AttributeError : %s' % err
        logging.warning(msg)

    return urlp

class Download(object):
    """ Class to download packages using urllib
        This class tries to previously download all necessary packages for
        Antergos installation using urllib """

    def __init__(self, pacman_cache_dir, cache_dir, callback_queue):
        """ Initialize Download class. Gets default configuration """
        self.pacman_cache_dir = pacman_cache_dir
        self.cache_dir = cache_dir
        self.callback_queue = callback_queue

        # Stores last issued event (to prevent repeating events)
        self.last_event = {}

    def start(self, downloads):
        """ Downloads using urllib """

        downloaded = 0
        total_downloads = len(downloads)

        self.queue_event('downloads_progress_bar', 'show')
        self.queue_event('downloads_percent', 0)

        while len(downloads) > 0:
            identity, element = downloads.popitem()

            self.queue_event('percent', 0)

            txt = _("Downloading %s %s (%d/%d)...")
            txt = txt % (element['identity'], element['version'], downloaded, total_downloads)
            self.queue_event('info', txt)

            try:
                total_length = int(element['size'])
            except TypeError as err:
                logging.warning(_("Metalink for package %s has no size info"), element['identity'])
                total_length = 0

            dst_cache_path = os.path.join(self.cache_dir, element['filename'])
            dst_path = os.path.join(self.pacman_cache_dir, element['filename'])

            if os.path.exists(dst_path):
                # File already exists (previous install?) do not download
                logging.warning(_("File %s already exists, Cnchi will not overwrite it"), element['filename'])
                self.queue_event('percent', 1.0)
                downloaded += 1
            elif os.path.exists(dst_cache_path):
                # We're lucky, the package is already downloaded in the cache the user has given us
                # let's copy it to our destination
                try:
                    shutil.copy(dst_cache_path, dst_path)
                    self.queue_event('percent', 1.0)
                    downloaded += 1
                    continue
                except FileNotFoundError:
                    pass
                except FileExistsError:
                    # print("File %s already exists" % element['filename'])
                    pass
            else:
                # Let's download our filename using url
                for url in element['urls']:
                    msg = _("Downloading file from url %s") % url
                    #logging.debug(msg)
                    download_error = True
                    percent = 0
                    completed_length = 0
                    urlp = url_open(url)
                    if urlp != None:
                        with open(dst_path, 'wb') as xzfile:
                            (data, download_error) = url_open_read(urlp)

                            while len(data) > 0 and download_error == False:
                                xzfile.write(data)
                                completed_length += len(data)
                                old_percent = percent
                                if total_length > 0:
                                    percent = round(float(completed_length / total_length), 2)
                                else:
                                    percent += 0.1
                                if old_percent != percent:
                                    self.queue_event('percent', percent)
                                (data, download_error) = url_open_read(urlp)

                            if not download_error:
                                downloaded += 1
                                break
                            else:
                                # try next mirror url
                                completed_length = 0
                                msg = _("Can't download %s, will try another mirror if available") % url
                                logging.warning(msg)
                    else:
                        # try next mirror url
                        msg = _("Can't open %s, will try another mirror if avaliable") % url
                        logging.warning(msg)

                if download_error:
                    # None of the mirror urls works.
                    # This is not a total disaster, maybe alpm will be able
                    # to download it for us later in pac.py
                    msg = _("Can't download %s, even after trying all available mirrors") % element['filename']
                    logging.warning(msg)

            downloads_percent = round(float(downloaded / total_downloads), 2)
            self.queue_event('downloads_percent', downloads_percent)

        self.queue_event('downloads_progress_bar', 'hide')

    def queue_event(self, event_type, event_text=""):
        """ Adds an event to Cnchi event queue """

        if self.callback_queue is None:
            if event_type != "percent":
                logging.debug(event_type + " : " + str(event_text))
            return

        if event_type in self.last_event:
            if self.last_event[event_type] == event_text:
                # do not repeat same event
                return

        self.last_event[event_type] = event_text

        try:
            # Add the event
            self.callback_queue.put_nowait((event_type, event_text))
        except queue.Full:
            pass
