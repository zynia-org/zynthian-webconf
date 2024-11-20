# -*- coding: utf-8 -*-
# ********************************************************************
# ZYNTHIAN PROJECT: Zynthian Web Configurator
#
# Pianoteq Config Handler
#
# Copyright (C) 2017-2024 Fernando Moyano <fernando@zynthian.org>
#
# ********************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
# ********************************************************************

import os
import sys
import psutil
import shutil
import logging
import tornado.web
from xml.etree import ElementTree
from subprocess import check_output, STDOUT

import zynconf
from zyngine.zynthian_engine_pianoteq import *
from lib.zynthian_config_handler import ZynthianBasicHandler

# sys.path.append(os.environ.get('ZYNTHIAN_UI_DIR'))

# ------------------------------------------------------------------------------
# Pianoteq Configuration
# ------------------------------------------------------------------------------


class PianoteqHandler(ZynthianBasicHandler):
    recipes_dir = os.environ.get('ZYNTHIAN_RECIPE_DIR', "/zynthian/zynthian-sys/scripts/recipes")

    @tornado.web.authenticated
    def get(self, errors=None):
        # self.pianoteq_autoconfig()
        info = get_pianoteq_binary_info()
        config = {
            'ZYNTHIAN_UPLOAD_MULTIPLE': False,
            'ZYNTHIAN_PIANOTEQ_TRIAL': info['trial'],
            'ZYNTHIAN_PIANOTEQ_VERSION': info['version_str'],
            'ZYNTHIAN_PIANOTEQ_PRODUCT': info['product'],
            'ZYNTHIAN_PIANOTEQ_LICENSE': self.get_license_key(),
            "ZYNTHIAN_PIANOTEQ_LIMIT_RATE": os.environ.get('ZYNTHIAN_PIANOTEQ_LIMIT_RATE', "1"),
            "ZYNTHIAN_PIANOTEQ_VOICE_LIMIT": os.environ.get('ZYNTHIAN_PIANOTEQ_VOICE_LIMIT', "32"),
            "ZYNTHIAN_PIANOTEQ_CPU_OVERLOAD_DETECTION": os.environ.get('ZYNTHIAN_PIANOTEQ_CPU_OVERLOAD_DETECTION', "1")
        }
        if errors:
            logging.error("Pianoteq Action Failed: %s" % format(errors))
        super().get("pianoteq.html", "Pianoteq", config, errors)

    @tornado.web.authenticated
    def post(self):
        errors = None
        try:
            action = self.get_argument('ZYNTHIAN_PIANOTEQ_ACTION')
        except:
            action = None
            logging.error(f"No action!")

        if action:
            try:
                errors = {
                    'INSTALL_PIANOTEQ': lambda: self.do_install_pianoteq(),
                    'ACTIVATE_LICENSE': lambda: self.do_activate_license(),
                    'SAVE_CONFIG': lambda: self.do_save_config()
                }[action]()
            except Exception as err:
                logging.error(err)

        self.get(errors)

    def do_install_pianoteq(self):
        errors = None
        filename = self.get_argument('ZYNTHIAN_PIANOTEQ_FILENAME')
        if filename:
            logging.info("Installing %s" % filename)

            # Install different type of files
            filename_parts = os.path.splitext(filename)
            # Pianoteq binaries
            if filename_parts[1].lower() == '.7z':
                errors = self.do_install_pianoteq_binary(filename)
            # Pianoteq instruments
            elif filename_parts[1].lower() == '.ptq':
                errors = self.do_install_pianoteq_ptq(filename)

            # Configure Pianoteq
            self.pianoteq_autoconfig()

        else:
            errors = 'Please, select a file to install'

        return errors

    def do_install_pianoteq_binary(self, filename):
        # Install new binary package
        command = self.recipes_dir + "/install_pianoteq_binary.sh {}; exit 0".format(filename)
        result = check_output(command, shell=True, stderr=STDOUT).decode("utf-8")
        # TODO! if result is OK, return None!
        return result

    def do_install_pianoteq_ptq(self, filename):
        try:
            # Create "Addons" directory if not already exist
            if not os.path.isdir(PIANOTEQ_ADDON_DIR):
                os.makedirs(PIANOTEQ_ADDON_DIR)
            # Copy uploaded file
            logging.info("Moving %s to %s" % (filename, PIANOTEQ_ADDON_DIR))
            shutil.move(filename, PIANOTEQ_ADDON_DIR + "/" + os.path.basename(filename))
        except Exception as e:
            logging.error("PTQ install failed: {}".format(e))
            return "PTQ install failed: {}".format(e)

    def do_activate_license(self):
        license_serial = self.get_argument('ZYNTHIAN_PIANOTEQ_LICENSE')
        logging.info("Configuring Pianoteq License Key: {}".format(license_serial))

        # Activate the License Key by calling Pianoteq binary
        command = "{} --prefs {} --activate {}; exit 0".format(PIANOTEQ_BINARY, PIANOTEQ_CONFIG_FILE, license_serial)
        try:
            result = check_output(command, shell=True, stderr=STDOUT).decode("utf-8")
        except Exception as e:
            logging.error(format(e))
            result = format(e)

        if result != "Activation Key Saved !\n":
            logging.error(result)
            return result
        else:
            self.pianoteq_autoconfig()

    def get_license_key(self):
        # xpath with fromstring doesn't work
        if os.path.exists(PIANOTEQ_CONFIG_FILE):
            root = ElementTree.parse(PIANOTEQ_CONFIG_FILE)
            try:
                for xml_value in root.iter("VALUE"):
                    if xml_value.attrib['name'] == 'serial':
                        return xml_value.attrib['val']
            except Exception as e:
                logging.error("Error parsing license: %s" % e)

    def do_save_config(self):
        config = {
            "ZYNTHIAN_PIANOTEQ_LIMIT_RATE": self.get_argument('ZYNTHIAN_PIANOTEQ_LIMIT_RATE'),
            "ZYNTHIAN_PIANOTEQ_VOICE_LIMIT": self.get_argument('ZYNTHIAN_PIANOTEQ_VOICE_LIMIT'),
            "ZYNTHIAN_PIANOTEQ_CPU_OVERLOAD_DETECTION": self.get_argument('ZYNTHIAN_PIANOTEQ_CPU_OVERLOAD_DETECTION')
        }
        errors = zynconf.save_config(config, updsys=True)

        # Restarts UI if pianoteq engine is running
        for process in psutil.process_iter():
            if process.name().startswith("Pianoteq"):
                self.restart_ui_flag = True
                break

        return errors

    def pianoteq_autoconfig(self):
        # Get and Save pianoteq binary options
        info = get_pianoteq_binary_info()
        if info:
            # Save envars
            config = {
                "ZYNTHIAN_PIANOTEQ_PRODUCT": info["product"],
                "ZYNTHIAN_PIANOTEQ_VERSION": info["version_str"],
                "ZYNTHIAN_PIANOTEQ_TRIAL": "1" if info["trial"] else "0"
            }
            if "voices" in info:
                config["ZYNTHIAN_PIANOTEQ_VOICE_LIMIT"] = info["voices"]
            if "cpu_overload_detection" in info:
                config["ZYNTHIAN_PIANOTEQ_CPU_OVERLOAD_DETECTION"] = info["cpu_overload_detection"]

            zynconf.save_config(config, updsys=True)

# *****************************************************************************
