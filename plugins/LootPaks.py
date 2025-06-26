import mobase
import os
import logging
import uuid
import re
from typing import List, Dict
from pathlib import Path
from PyQt6.QtCore import QDir
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QWidget, QMessageBox


class LootPaks(mobase.IPluginTool):
    _organizer: mobase.IOrganizer
    _mainWindow: QMainWindow
    _parentWidget: QWidget

    def __init__(self):
        super().__init__()
        self._init_logger()
        self._file_pattern = re.compile(
            r"re_chunk_000\.pak\.sub_000\.pak\.patch_(\d{3})\.pak"
        )

    def _init_logger(self) -> None:
        """初始化日志记录器"""
        self._logger = logging.getLogger("LootPaks")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        return True

    def name(self) -> str:
        return "LootPaks"

    def author(self) -> str:
        return "aqeqqq"

    def description(self) -> str:
        return "auto loot PAK"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.BETA)

    def isActive(self) -> bool:
        return self._organizer.pluginSetting(self.name(), "enabled") is True

    def settings(self) -> List[mobase.PluginSetting]:
        return [mobase.PluginSetting("enabled", "enable this plugin", True)]

    def displayName(self) -> str:
        return "Loot Paks"

    def tooltip(self) -> str:
        return "."

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget: QWidget):
        self._parentWidget = widget

    def _get_mod_paths(self) -> tuple:
        """获取关键路径信息"""
        mod_parent = self._organizer.modsPath()
        self._IPluginGame = self._organizer.managedGame()
        if self._IPluginGame is None:
            self._logger.error("No managed game found! Plugin cannot be initialized.")
            return False
        game_path = self._IPluginGame.gameDirectory().path()
        return mod_parent, game_path

    def _should_process_mod(self, mod: str) -> bool:
        """判断模组是否需要处理"""
        mod_state = self._organizer.modList().state(mod)
        return mod_state & mobase.ModState.ACTIVE.value

    def _handle_single_mod(self, mod_path: str, start_number: int) -> int:
        """处理单个模组返回新的起始编号"""
        if not mod_path.is_dir():
            self._logger.warning(f"Invalid mod path: {mod_path}")
            return start_number

        return self.processPakFiles(str(mod_path), start_number)

    def _create_temp_mapping(self, mod_path: Path) -> Dict[Path, Path]:
        """创建临时文件映射，仅处理根目录中的 .pak 文件"""
        temp_map = {}
        if (mod_path / ".NotLOOT").exists():
            self._logger.info(f"Skipped folder due to .NotLOOT file: {mod_path}")
            return {}
        for pak_file in mod_path.glob("*.pak"):  # 修改为 glob 以仅匹配根目录

            temp_name = f"{uuid.uuid4().hex}.pak"
            temp_path = pak_file.with_name(temp_name)
            if self._safe_rename(pak_file, temp_path):
                temp_map[temp_path] = pak_file
        return temp_map

    def _safe_rename(self, src: Path, dst: Path) -> bool:
        """安全的文件重命名操作"""
        try:
            src.rename(dst)
            # self._logger.info(f"Renamed: {src} -> {dst}")
            return True
        except PermissionError as e:
            self._logger.error(f"Permission denied: {src}")
            return False
        except OSError as e:
            self._logger.error(f"OS error: {e}")
            return False
        except Exception as e:
            self._logger.error(f"Rename failed: {src} -> {dst} | Error: {e}")
            return False

    def findStartNumber(self, gamePath: str) -> int:
        """使用正则表达式优化查找起始编号"""
        max_number = 0
        for root, _, files in os.walk(gamePath):
            for file in files:
                match = self._file_pattern.fullmatch(file)
                if match:
                    current_num = int(match.group(1))
                    max_number = max(max_number, current_num)
        return max_number + 1

    def processPakFiles(self, modPath: str, startNumber: int) -> int:
        """优化后的文件处理方法"""
        mod_path = Path(modPath)
        temp_map = self._create_temp_mapping(mod_path)

        current_number = startNumber
        for temp_path in sorted(temp_map.keys()):
            target_name = f"re_chunk_000.pak.sub_000.pak.patch_{current_number:03d}.pak"
            target_path = temp_path.with_name(target_name)
            if self._safe_rename(temp_path, target_path):
                self._logger.info(f"Renamed: {target_name}")
                current_number += 1
        # if current_number == startNumber:
        #     self._logger.info("No pak Skipped")
        return current_number

    def display(self):
        """优化后的主显示逻辑"""
        mod_parent, game_path = self._get_mod_paths()
        self._logger.info(f"Mod parent: {mod_parent}")
        self._logger.info(f"Game path: {game_path}")
        initial_number = self.findStartNumber(game_path)
        self._logger.info(f"Initial Pak number: {initial_number}")
        final_number = initial_number
        for mod in self._organizer.modList().allModsByProfilePriority():
            if not self._should_process_mod(mod):
                continue
            self._logger.info(f"Processing mod: {mod}")
            mod_path = Path(mod_parent) / mod
            final_number = self._handle_single_mod(mod_path, final_number)

        processed_count = final_number - initial_number
        self._show_completion_dialog(processed_count)

    def _show_completion_dialog(self, count: int):
        """显示完成对话框"""
        QMessageBox.information(
            self._parentWidget,
            "LOOT Done",
            f"LOOT {count} pak files",
        )


def createPlugin() -> mobase.IPlugin:
    return LootPaks()
