from gi.repository import Gtk, Gio

from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.view.configuration import LandscapeClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController



APPLICATION_ID="com.canonical.landscape-client.settings.ui"


class LandscapeSettingsApplicationController(Gtk.Application):
    """
    Core application controller for the landscape settings application.
    """


    def __init__(self):
        super(LandscapeSettingsApplicationController, self).__init__(
            application_id=APPLICATION_ID)
        self.connect("activate", self.setup_ui)


    def get_config(self):
        return LandscapeSetupConfiguration([])

    def setup_ui(self, data=None):
        config = self.get_config()
        controller = ConfigController(config)
        self.settings_dialog = LandscapeClientSettingsDialog(controller)
