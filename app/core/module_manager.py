# project_root/core/module_manager.py

import os
import importlib
import inspect

MODULES_FOLDER = os.path.join(os.path.dirname(__file__), "..", "modules")

class BaseModule:
    module_name = "base_module"
    module_type = "generic"
    def initialize(self):
        pass

class ModuleManager:
    def __init__(self):
        self.loaded_modules = {}

    def load_modules(self):
        for filename in os.listdir(MODULES_FOLDER):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_path = f"modules.{filename[:-3]}"
                self._import_and_register(module_path)

    def _import_and_register(self, module_path):
        try:
            mod = importlib.import_module(module_path)
            print(f"[DEBUG] Imported module: {module_path}")
            # or logger.debug(f"Imported module: {module_path}")
        except Exception as e:
            print(f"[ERROR] Failed to import module {module_path}: {e}")
            return

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseModule) and obj is not BaseModule:
                instance = obj()
                print(f"[DEBUG] Instantiating and initializing: {obj.__name__}")
                instance.initialize()
                self.loaded_modules[instance.module_name] = instance

    def get_module_by_type(self, mtype):
        for module in self.loaded_modules.values():
            if getattr(module, "module_type", None) == mtype:
                return module
        return None

    def get_module(self, module_name):
        return self.loaded_modules.get(module_name)
