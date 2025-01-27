# plugins/plugin_manager.py
import importlib
import pkgutil
import logging
from slack_bolt import App

logger = logging.getLogger(__name__)

def load_plugins(app: App, plugins_package: str = "plugins"):
    """
    Dynamically load all plugins in the specified plugins package.

    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
        plugins_package (str): The Python package where plugins are located.
    """
    package = importlib.import_module(plugins_package)
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            continue  # Skip sub-packages
        try:
            module = importlib.import_module(f"{plugins_package}.{module_name}")
            if hasattr(module, "register"):
                module.register(app)
                logger.info(f"Loaded plugin: {module_name}")
            else:
                logger.warning(f"Plugin {module_name} does not have a register(app) function.")
        except Exception as e:
            logger.error(f"Failed to load plugin {module_name}: {e}")
