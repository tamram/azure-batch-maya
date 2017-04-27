#-------------------------------------------------------------------------
#
# Azure Batch Maya Plugin
#
# Copyright (c) Microsoft Corporation.  All rights reserved.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the ""Software""), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
#--------------------------------------------------------------------------

import os
import logging

from api import MayaAPI as maya
from api import MayaCallbacks as callback

from ui_environment import EnvironmentUI

MAYA_VERSIONS = {"Maya 2016": "2015"}

SUPPORTED = [
    {"name": "Arnold", "plugin": "mtoa.", "license": True, "license_var": {"key":"solidangle_LICENSE", "value":"{port}@{host}"}},
]

EXTENSIONS = [".mll", ".bundle", ".py"]

DEFAULT = [
    'AbcBullet',
    'AbcExport',
    'AbcImport',
    'animImportExport',
    'ArubaTessellator',
    'atomImportExport',
    'AutodeskPacketFile',
    'autoLoader',
    'AzureBatch',
    'bullet',
    'cgfxShader',
    'cleanPerFaceAssignment',
    'clearcoat',
    'CloudImportExport',
    'ddsFloatReader',
    'deformerEvaluator',
    'dgProfiler',
    'DirectConnect',
    'dx11Shader',
    'fltTranslator',
    'Fur',
    'gameFbxExporter',
    'GamePipeline',
    'glslShader',
    'GPUBuiltInDeformer',
    'ge2Export',
    'gpuCache',
    'hlslShader',
    'ik2Bsolver',
    'ikSpringSolver',
    'matrixNodes',
    'mayaCharacterization',
    'mayaHIK',
    'MayaMuscle',
    'melProfiler',
    'modelingToolkit',
    'nearestPointOnMesh',
    'objExport',
    'OneClick',
    'OpenEXRLoader',
    'openInventor',
    'quatNodes',
    'retargeterNodes',
    'rotateHelper',
    'rtgExport',
    'sceneAssembly',
    'shaderFXPlugin',
    'stereoCamera',
    'studioImport',
    'tiffFloatReader',
    'Turtle',
    'Unfold3D',
    'VectorRender',
    'vrml2Export',
    'BifrostMain',
    'bifrostshellnode',
    'bifrostvisplugin',
    'fbxmaya',
    'Substance',
    'xgenMR',
    'xgenToolkit']

class AzureBatchEnvironment(object):
    
    def __init__(self, frame, call):

        self._log = logging.getLogger('AzureBatchMaya')
        self._call = call
        self._session = None

        self._server_plugins = []
        
        self._plugins = []
        self._version = "2015"

        self.ui = EnvironmentUI(self, frame, MAYA_VERSIONS.keys())
        self.warnings = []

        self.refresh()
        callback.after_new(self.ui.refresh)
        callback.after_read(self.ui.refresh)

    @property
    def plugins(self):
        return self._server_plugins

    @property
    def environment_variables(self):
        custom_vars = self.ui.get_env_vars()
        for plugin in self._plugins:
            custom_vars.update(plugin.get_variables())
        return custom_vars

    @property
    def version(self):
        return self._version

    @property
    def license(self):
        return self.ui.get_license_server()

    def configure(self, session):
        self._session = session

    def get_plugins(self):

        used_plugins = maya.plugins(query=True, pluginsInUse=True)
        extra_plugins = self.search_for_plugins()

        plugins = []

        for plugin in extra_plugins:
            support = [p for p in SUPPORTED if plugin.startswith(p["plugin"])]
            loaded = maya.plugins(plugin, query=True, loaded=True)

            plugin_ref = BatchPlugin(self, plugin, loaded, support)
            plugin_ref.is_used(used_plugins if used_plugins else [])
            plugins.append(plugin_ref)

        if self.warnings:
            warning = "The following plug-ins are used in the scene, but not yet supported.\nRendering may be affected.\n"
            for plugin in self.warnings:
                warning += plugin + "\n"
            maya.warning(warning)

        return plugins

    def search_for_plugins(self):
        found_plugins = []
        search_locations = os.environ["MAYA_PLUG_IN_PATH"].split(os.pathsep)

        for plugin_dir in search_locations:
            if os.path.isdir(plugin_dir):
                plugins = os.listdir(os.path.normpath(plugin_dir))
                for plugin in plugins:
                    found_plugins.append(plugin)

        found_plugins = list(set(found_plugins))
        return filter(self.is_default, found_plugins)

    def is_default(self, plugin):
        plugin, ext = os.path.splitext(plugin)
        if plugin in DEFAULT and ext in EXTENSIONS:
            return False

        elif ext in EXTENSIONS:
            return True

        else:
            return False

    def set_version(self, version):
        self._version = MAYA_VERSIONS.get(version, "2015")

    def refresh(self):
        self._server_plugins = []
        self.warnings = []
        for plugin in self._plugins:
            plugin.delete()

        self._plugins = self.get_plugins()


class BatchPlugin(object):

    def __init__(self, base, plugin, loaded, support):

        self.plugin = plugin
        self.label = plugin
        self.supported = bool(support)
        self.loaded = loaded
        self.used = False
        self.base = base
        self.license = False
        self.contents = []

        if self.supported:
            self.label = support[0]["name"]
            self.license = support[0]["license"]
            self.license_var = support[0].get("license_var", {})

        self.create_checkbox()

    def create_checkbox(self):
        self.checkbox = maya.check_box(label=self.label if self.supported else "Unsupported: {0}".format(self.label),
                                       value=False,
                                       onCommand=self.include,
                                       offCommand=self.exclude,
                                       parent=self.base.ui.plugin_layout,
                                       enable=self.supported)

        if self.license:
            self.license_check = maya.check_box(label="Use my license", value=False, parent=self.base.ui.plugin_layout, changeCommand=self.use_license, enable=False)
            self.custom_license_endp = maya.text_field( placeholderText='License Server', enable=False, parent=self.base.ui.plugin_layout)
            self.custom_license_port = maya.text_field( placeholderText='Port', enable=False, parent=self.base.ui.plugin_layout)
            self.contents.extend([self.license_check, self.custom_license_endp, self.custom_license_port])
        else:
            self.contents.append(maya.text(label="", parent=self.base.ui.plugin_layout))
        self.contents.append(self.checkbox)

    def is_used(self, used_plugins):
        self.used = False
        for plugin in used_plugins:
            if plugin == os.path.splitext(self.plugin)[0]:
                self.used = True
                break

        if self.loaded and self.supported and self.used:
            maya.check_box(self.checkbox, edit=True, value=True)
            if self.license:
                maya.check_box(self.license_check, edit=True, enable=True)
            self.base.plugins.append(self.label)

        if self.loaded and self.used and not self.supported:
            self.base.warnings.append(self.plugin)

    def use_license(self, license):
        if self.license:
            maya.text_field(self.custom_license_endp, edit=True, enable=license)
            maya.text_field(self.custom_license_port, edit=True, enable=license)

    def include(self, *args):
        self.base.plugins.append(self.label)

        if self.license:
            maya.check_box(self.license_check, edit=True, enable=True)

    def exclude(self, *args):
        if self.used:
            maya.warning("This plugin is currently in use. Excluding it may affect rendering.")

        if self.label in self.base.plugins: self.base.plugins.remove(self.label)
        if self.license:
            maya.check_box(self.license_check, edit=True, enable=False)

    def delete(self):
        for c in self.contents:
            maya.delete_ui(c, control=True)

    def get_variables(self):
        vars = {}
        if self.license and maya.check_box(self.license_check, query=True, value=True):
            license_key = self.license_var.get("key")
            license_val = self.license_var.get("value")
            
            host = str(maya.text_field(self.custom_license_endp, query=True, text=True))
            port = str(maya.text_field(self.custom_license_port, query=True, text=True))
            if host and port:
                vars[license_key] = license_val.format(host=host, port=port)

        return vars