# plugins/plugin_manager.py

import importlib
import pkgutil
import logging
from slack_bolt import App

# Configure the logger for plugin_manager
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def load_plugins(app: App, plugins_package: str = "plugins"):
    """
    Dynamically load and register all plugins within the specified plugins package.

    Args:
        app (App): The Slack Bolt App instance to register event listeners with.
        plugins_package (str): The Python package where plugins are located.
    """
    try:
        # Import the plugins package
        package = importlib.import_module(plugins_package)
    except ImportError as e:
        logger.error(f"Failed to import plugins package '{plugins_package}': {e}")
        return

    # Iterate over all modules in the plugins package
    for finder, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            logger.debug(f"Skipping sub-package '{module_name}' in '{plugins_package}'.")
            continue  # Skip sub-packages if any

        # Skip 'plugin_manager' itself to avoid recursive import
        if module_name == "plugin_manager":
            logger.debug("Skipping plugin_manager to avoid load conflict.")
            continue

        full_module_name = f"{plugins_package}.{module_name}"
        try:
            # Import the plugin module
            module = importlib.import_module(full_module_name)
            logger.info(f"Imported plugin module '{full_module_name}'.")
        except ImportError as e:
            logger.error(f"Failed to import plugin '{full_module_name}': {e}")
            continue  # Skip to the next plugin

        # Check if the plugin has a 'register' function
        if hasattr(module, "register") and callable(getattr(module, "register")):
            try:
                # Call the 'register' function, passing the Slack Bolt App instance
                module.register(app)
                logger.info(f"Registered plugin '{module_name}'.")
            except Exception as e:
                logger.error(f"Error registering plugin '{module_name}': {e}")
        else:
            logger.warning(f"Plugin '{module_name}' does not have a callable 'register(app)' function.")
