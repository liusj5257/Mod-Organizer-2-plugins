from __future__ import annotations

import re
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Union
import os
from dataclasses import dataclass

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import QDir
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
        if self.tree_widgets:
            # # 默认选中第一个分组树的第一个叶子节点
            # first_leaf = self.find_first_leaf(self.tree_widgets[0])
            # if first_leaf:
            #     self.tree_widgets[0].setCurrentItem(first_leaf)
            self.update_preview()

    def find_first_leaf(
        self, tree: QtWidgets.QTreeWidget
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """查找树中的第一个叶子节点"""
        root = tree.invisibleRootItem()
        stack = [root]
        while stack:
            item = stack.pop(0)
            for i in range(item.childCount()):
                child = item.child(i)
                if child.childCount() == 0:  # 叶子节点
                    return child
                stack.append(child)
        return None

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

        self.tree_widgets = []
        for group in self.groups:
            page_widget = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page_widget)

            tree_widget = QtWidgets.QTreeWidget()
            tree_widget.setHeaderHidden(True)  # 隐藏表头
            tree_widget.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )

            # 构建树形结构
            root = tree_widget.invisibleRootItem()
            path_nodes = {}  # 存储路径节点

            # 先按路径排序，确保父节点先创建
            sorted_options = sorted(group.options, key=lambda opt: opt.display_name)

            for option in sorted_options:
                parts = option.display_name.split("/")
                current_path = ""
                current_parent = root

                # 构建路径节点
                for i, part in enumerate(parts):
                    current_path = current_path + "/" + part if current_path else part

                    if current_path not in path_nodes:
                        node = QtWidgets.QTreeWidgetItem([part])
                        path_nodes[current_path] = node
                        current_parent.addChild(node)
                        # 只有叶子节点才可选中
                        if i == len(parts) - 1:
                            node.setData(
                                0, QtCore.Qt.ItemDataRole.UserRole, option.unique_name
                            )
                            node.setFlags(
                                node.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                            )
                            node.setCheckState(
                                0,
                                (
                                    QtCore.Qt.CheckState.Checked
                                    if option.unique_name in self.preselect
                                    else QtCore.Qt.CheckState.Unchecked
                                ),
                            )
                    else:
                        node = path_nodes[current_path]

                    current_parent = node

            tree_widget.collapseAll()
            tree_widget.itemSelectionChanged.connect(self.update_preview)
            self.tree_widgets.append(tree_widget)
            page_layout.addWidget(tree_widget)
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
            current_tree = self.tree_widgets[self.current_group_index]
            # 选中第一个叶子节点
            first_leaf = self.find_first_leaf(current_tree)
            if first_leaf:
                current_tree.setCurrentItem(first_leaf)

    def prev_group(self):
        """切换到上一个选项分组"""
        if self.current_group_index > 0:
            self.current_group_index -= 1
            self.stacked_widget.setCurrentIndex(self.current_group_index)
            self.update_buttons()
            current_tree = self.tree_widgets[self.current_group_index]
            # 选中第一个叶子节点
            first_leaf = self.find_first_leaf(current_tree)
            if first_leaf:
                current_tree.setCurrentItem(first_leaf)

    def select_all(self):
        """全选当前分组的选项"""
        current_tree = self.tree_widgets[self.current_group_index]
        root = current_tree.invisibleRootItem()
        self._set_tree_check_state(root, QtCore.Qt.CheckState.Checked)

    def deselect_all(self):
        """取消全选当前分组的选项"""
        current_tree = self.tree_widgets[self.current_group_index]
        root = current_tree.invisibleRootItem()
        self._set_tree_check_state(root, QtCore.Qt.CheckState.Unchecked)

    def _set_tree_check_state(
        self, parent: QtWidgets.QTreeWidgetItem, state: QtCore.Qt.CheckState
    ):
        """递归设置树节点的选中状态"""
        for i in range(parent.childCount()):
            child = parent.child(i)
            # 只有叶子节点才设置复选框状态
            if child.childCount() == 0:
                child.setCheckState(0, state)
            else:
                self._set_tree_check_state(child, state)

    def update_preview(self):
        """更新选项预览图和详细信息"""
        current_tree = self.tree_widgets[self.current_group_index]
        selected_items = current_tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        unique_name = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not unique_name:  # 非叶子节点没有数据
            return

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
        for tree_widget in self.tree_widgets:
            root = tree_widget.invisibleRootItem()
            stack = [root]
            while stack:
                parent = stack.pop()
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    if child.childCount() > 0:  # 非叶子节点，继续遍历
                        stack.append(child)
                    else:  # 叶子节点，检查是否选中
                        if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                            unique_name = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                            if unique_name:
                                selected.append(unique_name)
        return selected

    def tr(self, value: str) -> str:
        """国际化翻译方法"""
        return QApplication.translate("ModOptionsDialog", value)


class SB_Installer(mobase.IPluginInstallerSimple):
    """MOD安装器核心类，实现MO2插件接口"""

    RE_DESCRIPTION = re.compile(r"select([0-9]+)-description")
    RE_OPTION = re.compile(r"select([0-9]+)-option([0-9]+)")

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
        self._logger = logging.getLogger("SB_Installer")
        self._logger.setLevel(logging.DEBUG)

    def init(self, organizer: mobase.IOrganizer):
        """插件初始化方法"""
        self._organizer = organizer
        self._organizer.onAboutToRun(self._onAboutToRun)
        self._organizer.onUserInterfaceInitialized(self._onUiInitialized)
        translator = QtCore.QTranslator()
        translator.load("SB_Installer_zh_CN.qm")
        return True

    def _onUiInitialized(self, window: QtWidgets.QMainWindow):
        """当MO2用户界面完全初始化后调用"""
        mod_list = self._organizer.modList()
        if not mod_list.getMod("LogicModsStart_separator"):
            self._organizer.createMod(mobase.GuessedString("LogicModsStart_separator"))
        if not mod_list.getMod("LogicModsEnd_separator"):
            self._organizer.createMod(mobase.GuessedString("LogicModsEnd_separator"))
        self._organizer.modDataChanged(mod_list.getMod("LogicModsStart_separator"))

    def _onAboutToRun(self, executable: str, working_dir: QDir, args: str) -> bool:
        """在MO2即将运行时调用"""
        game_name = os.path.basename(executable)
        if game_name == "SB.exe" or game_name == "SB-Win64-Shipping.exe":
            self._logger.debug("Stellar Blade detected")
            allMods = self._organizer.modList().allModsByProfilePriority()
            mod_parent = self._organizer.modsPath()
            Logic = False
            for mod in allMods:
                mod_state = self._organizer.modList().state(mod)
                self._logger.debug(f"{mod} : {mod_state}")
                if mod.startswith("LogicModsStart"):
                    Logic = True
                    self._logger.info(f"find {mod}")
                    continue
                if mod.startswith("LogicModsEnd"):
                    self._logger.info(f"find: {mod}")
                    break
                if Logic and mod_state & mobase.ModState.ACTIVE.value:
                    self._logger.debug(f"process mod: {mod}")
                    mod_path = os.path.join(mod_parent, f"{mod}/SB/Content/Paks/~mods")
                    new_mod_path = os.path.join(
                        mod_parent, f"{mod}/SB/Content/Paks/LogicMods"
                    )
                    if os.path.exists(mod_path):
                        self._logger.info(f"rename {mod_path} to {new_mod_path}")
                        os.rename(mod_path, new_mod_path)
            return True
        else:
            self._logger.debug("Not Stellar Blade")
            return True
        return False

    def name(self):
        return "Stellar Blade Installer"

    def localizedName(self) -> str:
        return self.tr("Stellar Blade Installer")

    def author(self):
        return "aqeqqq"

    def description(self):
        return self.tr("Stellar Blade Installer")

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
        return 888

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

        def find_preview(current_tree: mobase.IFileTree) -> Optional[QtGui.QPixmap]:
            for entry in list(current_tree):
                if (
                    entry.isFile()
                    and entry.name().lower().startswith("preview")
                    and entry.suffix().lower() in ["jpg", "jpeg", "png"]
                ):
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

        def has_game_files(folder: mobase.IFileTree) -> bool:
            for entry in list(folder):
                if entry.isDir():
                    self._logger.debug(f"跳过目录: {entry.name()}")
                    continue
                if (
                    entry.hasSuffix("pak")
                    or entry.hasSuffix("ucas")
                    or entry.hasSuffix("utoc")
                    or entry.hasSuffix("bk2")
                ):
                    self._logger.debug(f"找到游戏文件: {entry.name()}")
                    return True
                elif entry.hasSuffix("png") and entry.name().lower() != "preview.png":
                    self._logger.debug(f"找到PNG文件: {entry.name()}, 认为是Images文件")
                    return True
                elif entry.hasSuffix("bmp") and entry.name().startswith("Splash"):
                    self._logger.debug(
                        f"找到特殊的Splash图片: {entry.name()}, 认为是Splash文件"
                    )
                    return True
                elif (
                    entry.isDir() and entry.name().startswith("ue4ss")
                ) or entry.name() == "dwmapi.dll":
                    self._logger.debug(
                        f"找到UE4SS相关文件夹或DLL: {entry.name()}, 认为是UE4SS文件"
                    )
                    return True
                else:
                    self._logger.debug(f"忽略未知文件: {entry.name()}")
            return False

        def find_options(
            root_tree: mobase.IFileTree,
            current_tree: mobase.IFileTree,
            rel_path: str = "",
        ) -> List[tuple[mobase.IFileTree, Optional[QtGui.QPixmap], dict]]:
            """递归查找所有包含游戏文件的文件夹选项"""
            options = []
            current_path = (
                f"{rel_path}/{current_tree.name()}" if rel_path else current_tree.name()
            )

            # 检查当前文件夹是否包含游戏文件
            if has_game_files(current_tree):
                preview = find_preview(current_tree)
                folder_info = {"name": current_path, "description": current_path}
                self._logger.debug(f"找到有效选项: {current_path}, 预览图: {preview}")
                options.append((current_tree, preview, folder_info))

            # 递归检查所有子文件夹
            for entry in list(current_tree):
                if entry.isDir():
                    # 递归时使用当前树的根节点（root_tree）来保持原始结构
                    options.extend(find_options(root_tree, entry, current_path))

            return options

        options = find_options(tree, tree)

        if not options:
            self._logger.debug("未找到任何有效的选项")
            return None
        elif len(options) == 1:
            self._logger.debug(f"找到单个选项: {options[0][2]['name']}")
            return options[0]
        else:
            self._logger.debug(f"找到 {len(options)} 个选项")
            return options

    def isArchiveSupported(self, tree: mobase.IFileTree) -> bool:
        """判断是否支持当前压缩包格式"""
        data_name = self._organizer.managedGame().dataDirectory().dirName()
        game_name = self._organizer.managedGame().gameName()
        self._logger.debug(
            f"检查压缩包支持: {data_name}, 游戏名: {game_name}, 压缩包树: {tree}"
        )
        if game_name == "Stellar Blade":
            self._logger.debug("当前游戏是Stellar Blade")
            base = self._getWizardArchiveBase(tree, data_name)
            return base is not None
        return

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

    def _wrap_in_target_path(self, tree: mobase.IFileTree) -> mobase.IFileTree:
        """将文件树包装到目标路径 SB/PAK/~MODS/ 下"""
        for entry in list(tree):
            if (
                entry.hasSuffix("pak")
                or entry.hasSuffix("ucas")
                or entry.hasSuffix("utoc")
            ):
                tree.move(entry, "SB/Content/Paks/~mods/")
            elif entry.hasSuffix("bk2"):
                tree.move(entry, "SB/Content/Movies/")
            elif entry.hasSuffix("png") and not entry.name().lower().startswith(
                "preview"
            ):
                tree.move(entry, "SB/Content/Images/SaveImage/")
            elif entry.name().startswith("Splash") and entry.hasSuffix("bmp"):
                tree.move(entry, "SB/Content/Splash/")
            elif (
                entry.isDir() and entry.name().startswith("ue4ss")
            ) or entry.name() == "dwmapi.dll":
                tree.move(entry, "SB/Binaries/Win64/")
            else:
                self._logger.error("未知文件类型，无法处理: " + entry.name())
        return tree

    def _handle_single_option(
        self, tree: mobase.IFileTree, base: tuple
    ) -> mobase.IFileTree:
        """处理单选项安装"""
        mod_tree, preview, modinfo = base
        new_tree = tree.createOrphanTree()
        new_tree.merge(mod_tree)
        self._clean_root_files(new_tree)
        return self._wrap_in_target_path(new_tree)

    def _handle_multiple_options(
        self, tree: mobase.IFileTree, base: list
    ) -> Union[mobase.InstallResult, mobase.IFileTree]:
        """处理多选项安装"""
        options_data = self._prepare_options_data(base)
        groups, unique_name_map = self._group_options(options_data)
        previous_selected = self._load_previous_selection()

        dialog = ModOptionsDialog(groups, self._parentWidget(), previous_selected)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            result = self._merge_selected_options(
                tree, dialog.selected_options(), unique_name_map
            )
            self._logger.debug(
                f"用户选择的选项: {dialog.selected_options()}, 合并后的文件树: {result}"
            )
            return self._wrap_in_target_path(result)
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
            if entry.isFile() and entry.suffix().lower() in {
                "ini",
                "jpg",
                "jpeg",
            }:
                tree.remove(entry.name())
            elif entry.isFile() and entry.name().startswith("preview"):
                tree.remove(entry.name())

    def tr(self, value: str) -> str:
        return QApplication.translate("SB_Installer", value)


def createPlugin() -> SB_Installer:
    return SB_Installer()
