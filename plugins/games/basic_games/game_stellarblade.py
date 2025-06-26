import logging
from ..basic_game import BasicGame
from PyQt6.QtCore import QFileInfo
import mobase


class stellarblade(BasicGame):
    Name = "stellar blade"
    Author = "aqeqqq"
    Version = "1.0.0"

    GameName = "Stellar Blade"
    GameShortName = "stellarblade"
    GameNexusName = "stellarblade"
    GameSteamId = 3489700
    GameNexusId = 7804
    GameBinary = "SB\\Binaries\\Win64\\SB-Win64-Shipping.exe"
    GameSaveExtension = "sav"
    GameSavesDirectory = "%USERPROFILE%/AppData/Local/SB/Saved/SaveGames"
    GameDataPath = ""
    GameDocumentsDirectory = "%USERPROFILE%/AppData/Local/SB/Saved/Config/WindowsNoEditor/"
    GameIniFiles = "Engine.ini"
    _logger = logging.getLogger("stellarblade")

    def __init__(self):
        BasicGame.__init__(self)

    def init(self, organizer: mobase.IOrganizer):
        return BasicGame.init(self, organizer)

    def executables(self):
        return [
            mobase.ExecutableInfo(
                "Stellar Blade",
                QFileInfo(self.gameDirectory().absoluteFilePath(self.binaryName())),
            ).withArgument("SB -DistributionPlatform=Steam"),
        ]
