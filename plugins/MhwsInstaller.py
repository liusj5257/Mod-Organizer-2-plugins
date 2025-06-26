from __future__ import annotations

import re
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Union, cast
from dataclasses import dataclass

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import QApplication

import mobase


@dataclass
class GroupOption:
    """表示分组选项的配置项"""

    unique_name: str
    display_name: str
    description: str
    preview: Optional[QtGui.QPixmap] = None


@dataclass
class GroupItem:
    """表示一个选项分组"""

    name: str
    options: list[GroupOption]


class ModOptionsDialog(QtWidgets.QDialog):
    """选项选择对话框，用于显示和管理MOD安装选项"""

    def __init__(
        self,
        groups: list[GroupItem],
        parent: QtWidgets.QWidget | None = None,
        preselect: list[str] = None,
    ):
        """
        初始化对话框
        :param groups: 分组选项列表
        :param parent: 父级窗口部件
        :param preselect: 预设选中的选项唯一名称列表
        """
        super().__init__(parent)
        self._selected_options: list[str] = []
        self.groups = groups
        self.preselect = preselect or []
        self.current_group_index = 0

        # 创建选项映射关系
        self.preview_map = {}
        self.modinfo_map = {}
        for group in groups:
            for option in group.options:
                self.preview_map[option.unique_name] = option.preview
                self.modinfo_map[option.unique_name] = option.description

        self.setup_ui()

    def setup_ui(self):
        """初始化用户界面布局"""
        self.setWindowTitle(self.tr("Select Options"))
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)

        self._setup_graphics_view(splitter)
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)

        self._setup_title_label(right_layout)
        self._setup_modinfo_text(right_layout)
        self._setup_stacked_widget(right_layout)
        self._setup_buttons(right_layout)

        splitter.addWidget(right_widget)
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(splitter)

        self.update_buttons()
        if self.list_widgets:
            self.list_widgets[0].setCurrentRow(0)
            self.update_preview()

    def _setup_graphics_view(self, splitter: QtWidgets.QSplitter):
        """初始化左侧图片预览区域"""
        self.graphics_view = QtWidgets.QGraphicsView()
        self.graphics_view.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.graphics_view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.graphics_view.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.graphics_view.setResizeAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.graphics_view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.graphics_view.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.graphics_view.viewport().installEventFilter(self)

        self.scene = QtWidgets.QGraphicsScene()
        self.graphics_view.setScene(self.scene)
        self.graphics_view.setStyleSheet("border: 1px solid #444; background: #2A2A2A;")
        self.graphics_view.setMinimumSize(600, 600)
        splitter.addWidget(self.graphics_view)

    def _setup_title_label(self, layout: QtWidgets.QVBoxLayout):
        """初始化分组标题标签"""
        self.title_label = QtWidgets.QLabel(self.groups[self.current_group_index].name)
        self.title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; margin-bottom: 10px;"
        )
        layout.addWidget(self.title_label)

    def _setup_modinfo_text(self, layout: QtWidgets.QVBoxLayout):
        """初始化模组信息显示区域"""
        self.modinfo_text = QtWidgets.QTextEdit()
        self.modinfo_text.setReadOnly(True)
        self.modinfo_text.setStyleSheet("font-family: Consolas; font-size: 16px;")
        layout.addWidget(self.modinfo_text, stretch=1)

    def _setup_stacked_widget(self, layout: QtWidgets.QVBoxLayout):
        """初始化选项分页组件"""
        self.stacked_widget = QtWidgets.QStackedWidget()
        layout.addWidget(self.stacked_widget, stretch=6)

        self.list_widgets = []
        for group in self.groups:
            page_widget = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page_widget)

            list_widget = QtWidgets.QListWidget()
            list_widget.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )
            for option in group.options:
                item = QtWidgets.QListWidgetItem(option.display_name)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, option.unique_name)
                item.setCheckState(
                    QtCore.Qt.CheckState.Checked
                    if option.unique_name in self.preselect
                    else QtCore.Qt.CheckState.Unchecked
                )
                list_widget.addItem(item)
            list_widget.itemSelectionChanged.connect(self.update_preview)
            self.list_widgets.append(list_widget)
            page_layout.addWidget(list_widget)
            self.stacked_widget.addWidget(page_widget)

    def _setup_buttons(self, layout: QtWidgets.QVBoxLayout):
        """初始化底部操作按钮"""
        button_layout = QtWidgets.QHBoxLayout()
        self.select_all_btn = QtWidgets.QPushButton(self.tr("Select All"))
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)

        self.deselect_btn = QtWidgets.QPushButton(self.tr("Deselect All"))
        self.deselect_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_btn)

        self.prev_btn = QtWidgets.QPushButton(self.tr("Previous"))
        self.prev_btn.clicked.connect(self.prev_group)
        button_layout.addWidget(self.prev_btn)

        self.next_btn = QtWidgets.QPushButton(self.tr("Next"))
        self.next_btn.clicked.connect(self.next_group)
        button_layout.addWidget(self.next_btn)

        self.cancel_btn = QtWidgets.QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def eventFilter(self, source, event):
        """处理图形视图的滚轮缩放事件"""
        if (
            source is self.graphics_view.viewport()
            and event.type() == QtCore.QEvent.Type.Wheel
        ):
            self.handle_wheel_zoom(event)
            return True
        return super().eventFilter(source, event)

    def handle_wheel_zoom(self, event: QtGui.QWheelEvent):
        """处理鼠标滚轮缩放操作"""
        current_scale = self.graphics_view.transform().m11()
        zoom_factor = 1.001 ** event.angleDelta().y()
        new_scale = current_scale * zoom_factor

        if 0.01 <= new_scale <= 50:
            old_center = self.graphics_view.mapToScene(
                self.graphics_view.viewport().rect().center()
            )
            self.graphics_view.scale(zoom_factor, zoom_factor)
            view_rect = self.graphics_view.mapToScene(
                self.graphics_view.viewport().rect()
            ).boundingRect()
            image_rect = self.scene.itemsBoundingRect()
            if view_rect.contains(image_rect):
                self.graphics_view.centerOn(image_rect.center())

    def update_buttons(self):
        """更新导航按钮状态"""
        self.prev_btn.setEnabled(self.current_group_index > 0)
        if self.current_group_index == len(self.groups) - 1:
            self.next_btn.setText(self.tr("Finish"))
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.accept)
        else:
            self.next_btn.setText(self.tr("Next"))
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.next_group)
        self.title_label.setText(self.groups[self.current_group_index].name)

    def next_group(self):
        """切换到下一个选项分组"""
        if self.current_group_index < len(self.groups) - 1:
            self.current_group_index += 1
            self.stacked_widget.setCurrentIndex(self.current_group_index)
            self.update_buttons()
            current_list = self.list_widgets[self.current_group_index]
            if current_list.count() > 0:
                current_list.setCurrentRow(0)

    def prev_group(self):
        """切换到上一个选项分组"""
        if self.current_group_index > 0:
            self.current_group_index -= 1
            self.stacked_widget.setCurrentIndex(self.current_group_index)
            self.update_buttons()
            current_list = self.list_widgets[self.current_group_index]
            if current_list.count() > 0:
                current_list.setCurrentRow(0)

    def select_all(self):
        """全选当前分组的选项"""
        current_list = self.list_widgets[self.current_group_index]
        for i in range(current_list.count()):
            item = current_list.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Checked)

    def deselect_all(self):
        """取消全选当前分组的选项"""
        current_list = self.list_widgets[self.current_group_index]
        for i in range(current_list.count()):
            item = current_list.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def update_preview(self):
        """更新选项预览图和详细信息"""
        current_list = self.list_widgets[self.current_group_index]
        selected_items = current_list.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        unique_name = item.data(QtCore.Qt.ItemDataRole.UserRole)

        self.scene.clear()
        preview = self.preview_map.get(unique_name)
        if preview:
            pixmap_item = QtWidgets.QGraphicsPixmapItem(preview)
            pixmap_item.setTransformationMode(
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            pixmap_item.setPos(-preview.width() / 2, -preview.height() / 2)
            self.scene.addItem(pixmap_item)
            self.graphics_view.fitInView(
                pixmap_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio
            )
        else:
            text_item = self.scene.addText(self.tr("无可用预览"))
            text_item.setDefaultTextColor(QtGui.QColor("#FFFFFF"))
            text_item.setPos(
                -text_item.boundingRect().width() / 2,
                -text_item.boundingRect().height() / 2,
            )

        self.modinfo_text.setPlainText(
            self.modinfo_map.get(unique_name, self.tr("无modinfo信息"))
        )

    def resizeEvent(self, event: QtGui.QResizeEvent):
        """窗口大小变化事件处理"""
        super().resizeEvent(event)
        if self.scene.items():
            self.graphics_view.fitInView(
                self.scene.itemsBoundingRect(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            )

    def selected_options(self) -> list[str]:
        """获取所有选中的选项唯一名称"""
        selected = []
        for list_widget in self.list_widgets:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.checkState() == QtCore.Qt.CheckState.Checked:
                    selected.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return selected

    def tr(self, value: str) -> str:
        """国际化翻译方法"""
        return QApplication.translate("ModOptionsDialog", value)


class MhwsInstaller(mobase.IPluginInstallerSimple):
    """MOD安装器核心类，实现MO2插件接口"""

    RE_DESCRIPTION = re.compile(r"select([0-9]+)-description")
    RE_OPTION = re.compile(r"select([0-9]+)-option([0-9]+)")

    _organizer: mobase.IOrganizer
    _installerOptions: Dict[str, List[str]]
    _installerUsed: bool

    def __init__(self):
        super().__init__()
        self._init_logger()
        self.current_mod = None
        self.new_mod = None
        self._pending_selected_options = None

    def _init_logger(self) -> None:
        """初始化日志记录器"""
        self._logger = logging.getLogger("LootPaks")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer):
        """插件初始化方法"""
        self._organizer = organizer
        translator = QtCore.QTranslator()
        translator.load("MhwsInstaller_zh_CN.qm")
        return True

    def name(self):
        return "MHWS Installer"

    def localizedName(self) -> str:
        return self.tr("MHWS Installer")

    def author(self):
        return "aqeqqq"

    def description(self):
        return self.tr("MHWS")

    def version(self):
        return mobase.VersionInfo(1, 0, 0)

    def isActive(self):
        return self._organizer.pluginSetting(self.name(), "enabled")

    def settings(self):
        return [
            mobase.PluginSetting("enabled", "check to enable this plugin", True),
        ]

    def priority(self) -> int:
        """返回安装器优先级"""
        return 999

    def isManualInstaller(self) -> bool:
        """返回是否是手动安装器"""
        return False

    def onInstallationStart(
        self,
        archive: str,
        reinstallation: bool,
        current_mod: Optional[mobase.IModInterface],
    ):
        """安装开始时的回调方法"""
        self._installerUsed = False
        self._installerOptions = {}
        self.current_mod = current_mod

    def onInstallationEnd(
        self, result: mobase.InstallResult, new_mod: Optional[mobase.IModInterface]
    ):
        """安装结束时的回调方法"""
        self.new_mod = new_mod
        if (
            result == mobase.InstallResult.SUCCESS
            and self._pending_selected_options is not None
            and self.new_mod is not None
        ):
            self.new_mod.setPluginSetting(
                self.name(), "selected_options", self._pending_selected_options
            )
            self._logger.debug(
                f"配置已保存到 {self.new_mod.name()}: {self._pending_selected_options}"
            )
            self._pending_selected_options = None

        if (
            result != mobase.InstallResult.SUCCESS
            or not self._installerUsed
            or not new_mod
        ):
            return

        new_mod.clearPluginSettings(self.name())
        for i, desc in enumerate(self._installerOptions):
            new_mod.setPluginSetting(self.name(), f"select{i}-description", desc)
            for iopt, opt in enumerate(self._installerOptions[desc]):
                new_mod.setPluginSetting(self.name(), f"select{i}-option{iopt}", opt)

    def _getWizardArchiveBase(self, tree: mobase.IFileTree, data_name: str) -> Union[
        tuple[mobase.IFileTree, Optional[QtGui.QPixmap], dict],
        List[tuple[mobase.IFileTree, Optional[QtGui.QPixmap], dict]],
        None,
    ]:
        """解析压缩包结构并获取有效选项数据"""

        def read_modinfo(entry: mobase.IFileTree) -> dict:
            """读取modinfo配置文件"""
            modinfo_entry = entry.find("modinfo.ini", mobase.FileTreeEntry.FILE)
            if modinfo_entry:
                try:
                    paths = self._manager().extractFile(modinfo_entry, silent=True)
                    properties = {}
                    with open(paths, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and "=" in line:
                                key, value = line.split("=", 1)
                                key = key.strip().lower()
                                value = value.strip()
                                properties[key] = value
                    return properties
                except Exception as e:
                    self._logger.error(f"读取modinfo.ini失败: {str(e)}")
            return {}

        def find_preview(current_tree: mobase.IFileTree) -> Optional[QtGui.QPixmap]:
            """查找预览图片"""
            for entry in current_tree:
                if entry.isFile() and entry.suffix().lower() in ["jpg", "jpeg", "png"]:
                    try:
                        paths = self._manager().extractFile(entry, silent=False)
                        data = open(paths, "rb").read()
                        if not data:
                            continue
                        pixmap = QtGui.QPixmap()
                        if pixmap.loadFromData(data):
                            return pixmap
                    except Exception as e:
                        self._logger.error(
                            f"加载备用预览图失败 {entry.name()}: {str(e)}"
                        )
            return None

        # 根目录检查
        entry = tree.find("modinfo.ini", mobase.FileTreeEntry.FILE)
        if entry:
            preview = find_preview(tree)
            modinfo_text = read_modinfo(tree)
            return (tree, preview, modinfo_text)

        # 单文件夹检查
        if len(tree) == 1 and isinstance((root := tree[0]), mobase.IFileTree):
            return self._getWizardArchiveBase(root, data_name)

        # 多选项处理
        option_trees = []
        for entry in tree:
            if entry.isDir():
                modinfo_entry = entry.find("modinfo.ini", mobase.FileTreeEntry.FILE)
                if modinfo_entry:
                    preview = find_preview(entry)
                    modinfo_text = read_modinfo(entry)
                    option_trees.append((entry, preview, modinfo_text))

        return option_trees if option_trees else None

    def isArchiveSupported(self, tree: mobase.IFileTree) -> bool:
        """判断是否支持当前压缩包格式"""
        data_name = self._organizer.managedGame().dataDirectory().dirName()
        base = self._getWizardArchiveBase(tree, data_name)
        return base is not None

    def install(
        self,
        name: mobase.GuessedString,
        tree: mobase.IFileTree,
        version: str,
        nexus_id: int,
    ) -> Union[mobase.InstallResult, mobase.IFileTree]:
        """执行安装过程"""
        self._logger.debug("开始安装流程")
        mod_name = str(name)
        self._initialize_current_mod(mod_name)

        data_name = self._organizer.managedGame().dataDirectory().dirName()
        base = self._getWizardArchiveBase(tree, data_name)

        if not base:
            return mobase.InstallResult.NOT_ATTEMPTED

        if isinstance(base, tuple):
            return self._handle_single_option(tree, base)

        if isinstance(base, list):
            return self._handle_multiple_options(tree, base)

        return mobase.InstallResult.NOT_ATTEMPTED

    def _initialize_current_mod(self, mod_name: str):
        """初始化当前MOD实例"""
        existing_mod = self._organizer.modList().getMod(mod_name)
        if not self.current_mod and existing_mod:
            self.current_mod = existing_mod

    def _handle_single_option(
        self, tree: mobase.IFileTree, base: tuple
    ) -> mobase.IFileTree:
        """处理单选项安装"""
        mod_tree, preview, modinfo = base
        new_tree = tree.createOrphanTree()
        new_tree.merge(mod_tree)
        self._clean_root_files(new_tree)
        return new_tree

    def _handle_multiple_options(
        self, tree: mobase.IFileTree, base: list
    ) -> Union[mobase.InstallResult, mobase.IFileTree]:
        """处理多选项安装"""
        options_data = self._prepare_options_data(base)
        groups, unique_name_map = self._group_options(options_data)
        previous_selected = self._load_previous_selection()

        dialog = ModOptionsDialog(groups, self._parentWidget(), previous_selected)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return self._merge_selected_options(
                tree, dialog.selected_options(), unique_name_map
            )
        return mobase.InstallResult.CANCELED

    def _prepare_options_data(self, base: list) -> list:
        """准备选项显示数据"""
        return [
            {
                "display_name": entry[2].get("name", entry[0].name()),
                "preview": entry[1],
                "modinfo": entry[2],
                "entry": entry[0],
            }
            for entry in base
        ]

    def _group_options(self, options_data: list) -> tuple[list[GroupItem], dict]:
        """分组处理安装选项"""
        grouped_options = defaultdict(list)
        unique_name_map = {}

        for data in options_data:
            group_name = data["modinfo"].get("nameasbundle", "default")
            unique_name = f"{group_name}:{data['display_name']}"
            grouped_options[group_name].append(
                GroupOption(
                    unique_name=unique_name,
                    display_name=data["display_name"],
                    description=data["modinfo"]
                    .get("description", "无描述信息")
                    .replace("\\n", "\n"),
                    preview=data["preview"],
                )
            )
            unique_name_map[unique_name] = data["entry"]

        for group_name, options in grouped_options.items():
            grouped_options[group_name] = sorted(options, key=lambda x: x.display_name)

        groups = [GroupItem(name=k, options=v) for k, v in grouped_options.items()]
        return groups, unique_name_map

    def _load_previous_selection(self) -> list:
        """加载历史选中项"""
        if self.current_mod:
            return self.current_mod.pluginSetting(self.name(), "selected_options") or []
        return []

    def _merge_selected_options(
        self, tree: mobase.IFileTree, selected_names: list, unique_name_map: dict
    ) -> mobase.IFileTree:
        """合并用户选择的选项到文件树"""
        self._pending_selected_options = selected_names
        new_tree = tree.createOrphanTree()
        for unique_name in selected_names:
            if entry := unique_name_map.get(unique_name):
                new_tree.merge(entry)
        self._clean_root_files(new_tree)
        return new_tree

    def _clean_root_files(self, tree: mobase.IFileTree):
        """清理根目录临时文件"""
        for entry in list(tree):
            if entry.isFile() and entry.suffix().lower() in {"ini", "jpg", "png"}:
                tree.remove(entry.name())

    def tr(self, value: str) -> str:
        return QApplication.translate("MhwsInstaller", value)


def createPlugin() -> MhwsInstaller:
    return MhwsInstaller()
