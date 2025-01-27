# plugins/plugin_manager.py
#"""
#Plugin manager to load and initialize plugin modules. 
#Allows a minimal "core" while advanced features live in separate files.
#"""

import importlib
import os

PLUGIN_MODULES = [
    "plugins.gpt_interaction",
    "plugins.self_upgrade",
    "plugins.rate_limiting",
    "plugins.rollback",
    "plugins.model_manager",
]

class PluginManager:
    @staticmethod
    def load_plugins(app):
        """
        Dynamically import and initialize the defined plugin modules.
        Each plugin file can register its handlers with the Slack 'app' object.
        """
        for module_path in PLUGIN_MODULES:
            importlib.import_module(module_path)  # side effect: modules attach to 'app'
        print("Plugins loaded:", PLUGIN_MODULES)
