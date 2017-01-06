#
# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2016  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


#
# The file was taken from eric 4.4.3 and adopted for codimension.
# Original copyright:
# Copyright (c) 2007 - 2010 Detlev Offenbach <detlev@die-offenbachs.de>
#

"""Splash screen implementation"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QSplashScreen
from utils.pixmapcache import getPixmap


class SplashScreen(QSplashScreen):

    """Splash screen class"""

    def __init__(self):
        self.labelAlignment = Qt.Alignment(Qt.AlignBottom |
                                           Qt.AlignRight |
                                           Qt.AlignAbsolute)

        QSplashScreen.__init__(self, None, getPixmap('splash.png'))

        self.show()
        QApplication.flush()

    def showMessage(self, msg):
        """Show the message in the bottom part of the splashscreen"""
        QSplashScreen.showMessage(self, msg,
                                  self.labelAlignment, QColor(Qt.black))
        QApplication.processEvents()

    def clearMessage(self):
        """Clear the splash screen message"""
        QSplashScreen.clearMessage(self)
        QApplication.processEvents()
