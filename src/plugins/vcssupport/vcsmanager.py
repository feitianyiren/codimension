#
# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010  Sergey Satskiy sergey.satskiy@gmail.com
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
# $Id$
#

"""
VCS plugin support: manager to keep track of the VCS plugins and file status
"""

import os.path
import logging
from statuscache import VCSStatusCache
from utils.settings import Settings
from utils.globals import GlobalData
from indicator import VCSIndicator
from utils.project import CodimensionProject
from PyQt4.QtCore import QObject, SIGNAL
from vcspluginthread import VCSPluginThread
from plugins.categories.vcsiface import VersionControlSystemInterface


# Indicator used by IDE to display errors while retrieving item status
IND_VCS_ERROR = -2


class VCSPluginDescriptor:
    " Holds information about a single active plugin "

    def __init__( self, plugin ):
        self.plugin = plugin
        self.thread = None                  # VCSPluginThread
        self.indicators = {}                # ID -> VCSIndicator

        self.__getPluginIndicators()
        self.thread = VCSPluginThread( plugin )
        self.thread.start()
        return

    def stopThread( self ):
        " Stops the plugin thread synchronously "
        self.thread.stop()  # Sends request
        self.thread.wait()  # Joins the thread
        return

    def requestStatus( self, path, flag, urgent = False ):
        " Requests the item status asynchronously "
        self.thread.addRequest( path, flag, urgent )
        return

    def getPluginName( self ):
        " Safe plugin name "
        try:
            return self.plugin.getName()
        except:
            return "Unknown (could not retrieve)"

    def __getPluginIndicators( self ):
        " Retrieves indicators from the plugin "
        try:
            for indicatorDesc in self.plugin.getObject().getCustomIndicators():
                try:
                    indicator = VCSIndicator( indicatorDesc )
                    if indicator.identifier < 0:
                        logging.error( "Custom VCS plugin '" +
                                       self.getPluginName() +
                                       "' indicator identifier " +
                                       str( indicator.identifier ) +
                                       " is invalid. It must be >= 0. "
                                       "Ignore and continue." )
                    else:
                        self.indicators[ indicator.identifier ] = indicator
                except Exception, exc:
                    logging.error( "Error getting custom VCS plugin '" +
                                   self.getPluginName() +
                                   "' indicator: " + str( exc ) )
        except Exception, exc:
            logging.error( "Error getting custom indicators for a VCS plugin " +
                           self.getPluginName() + ". Exception: " +
                           str( exc ) )
        return



class VCSManager( QObject ):
    " Manages the VCS plugins "

    def __init__( self ):
        QObject.__init__( self )

        self.dirCache = VCSStatusCache()    # Path -> VCSStatus
        self.fileCache = VCSStatusCache()   # Path -> VCSStatus
        self.activePlugins = {}             # Plugin ID -> VCSPluginDescriptor
        self.systemIndicators = {}          # ID -> VCSIndicator

        self.__firstFreeIndex = 0

        self.__readSettingsIndicators()

        self.connect( GlobalData().project, SIGNAL( 'projectChanged' ),
                      self.__onProjectChanged )
        self.connect( GlobalData().pluginManager, SIGNAL( 'PluginActivated' ),
                      self.__onPluginActivated )

        # Plugin deactivation must be done via dismissPlugin(...)
        return

    def __getNewPluginIndex( self ):
        " Provides a new plugin index "
        index = self.__firstFreeIndex
        self.__firstFreeIndex += 1
        return index

    def __readSettingsIndicators( self ):
        " Reads the system indicators "
        for indicLine in Settings().vcsindicators:
            indicator = VCSIndicator( indicLine )
            self.systemIndicators[ indicator.identifier ] = indicator
        return

    def __onPluginActivated( self, plugin ):
        " Triggered when a plugin is activated "
        if plugin.categoryName != "VersionControlSystemInterface":
            return

        newPluginIndex = self.__getNewPluginIndex()
        self.activePlugins[ newPluginIndex ] = VCSPluginDescriptor( plugin )

        if len( self.activePlugins ) == 1 and GlobalData().project.isLoaded():
            # This is the first plugin and a project is there
            self.__populateProjectDirectories()
        self.__sendDirectoryRequests( newPluginIndex )
        return

    def __populateProjectDirectories( self ):
        " Populates the project directories in the dirCache "
        project = GlobalData().project
        for path in project.filesList:
            if path.endswith( os.path.sep ):
                self.dirCache.updateStatus( path, None, None, None )
        return

    def __onProjectChanged( self, what ):
        " Triggered when a project has changed "
        if what == CodimensionProject.CompleteProject:
            self.dirCache.clear()
            self.fileCache.clear()
            if len( self.activePlugins ) == 0:
                return

            # There are some plugins
            if not GlobalData().project.isLoaded():
                return

            for pluginID in self.activePlugins.keys():
                self.__populateProjectDirectories( pluginID )
            return

        # Here: files or directories have changed
        return

    def __sendDirectoryRequests( self, pluginID ):
        " Sends the directory requests to the given plugins "
        descriptor = self.activePlugins[ pluginID ]
        for path in self.dirCache.cache.keys():
            descriptor.requestStatus( path,
                                      VersionControlSystemInterface.REQUEST_DIRECTORY )
        return

    def dismissAllPlugins( self ):
        " Stops all the plugin threads "
        for identifier, descriptor in self.activePlugins.iteritems():
            descriptor.stopThread()

        self.dirCache.clear()
        self.fileCache.clear()
        self.activePlugins = {}
        return

    def dismissPlugin( self, plugin ):
        " Stops the plugin thread and cleans the plugin data "
        pluginID = None
        for identifier, descriptor in self.activePlugins.iteritems():
            if descriptor.getPluginName() == plugin.getName():
                pluginID = identifier
                descriptor.stopThread()
                self.fileCache.dismissPlugin( pluginID,
                                              self.sendStatusNotification )
                self.dirCache.dismissPlugin( pluginID,
                                             self.sendStatusNotification )

        if pluginID:
            del self.activePlugins[ identifier ]
        return

    def requestStatus( self, path,
                       flag = VersionControlSystemInterface.REQUEST_ITEM_ONLY ):
        " Provides the path status asynchronously via sending a signal "
        status = self.dirCache.getStatus( path )
        if not status:
            status = self.fileCache.getStatus( path )
        if status:
            self.sendStatusNotification( path, status.pluginID,
                                         status.indicatorID, status.message )
        else:
            for _, descriptor in self.activePlugins.iteritems():
                descriptor.requestStatus( path, flag, True )
        return

    def setLocallyModified( self, path ):
        " Sets the item status as locally modified "
        pass

    def sendStatusNotification( self, path, pluginID, indicatorID, message ):
        " Sends a signal that about a status of the path "
        self.emit( SIGNAL( "VCSStatus" ), path, pluginID, indicatorID, message )
        return
